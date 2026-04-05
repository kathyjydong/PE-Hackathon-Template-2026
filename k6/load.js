import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";

/** Count X-Cache on successful redirects (verify Redis after warmup — expect mostly HIT for k6hot) */
const resolveCacheHit = new Counter("resolve_x_cache_HIT");
const resolveCacheMiss = new Counter("resolve_x_cache_MISS");

/**
 * Benchmark: **resolve (redirect) only** in the default function — p95 reflects the hot path, not /health or /shorten.
 * Setup still seeds via /health + /shorten once.
 *
 * Do NOT set BASE_URL to :5000/:5001 unless K6_DIRECT_APP=1 — that bypasses nginx.
 *
 * Host k6 (same machine as Docker Desktop):
 *   k6 run k6/load.js
 *
 * Mixed workload (health + shorten + resolve) for other experiments:
 *   K6_MIXED_WORKLOAD=1 k6 run k6/load.js
 *
 * k6 inside Docker (grafana/k6):
 *   docker run --rm -e K6_IN_DOCKER=1 -v "$PWD:/work" grafana/k6 run /work/k6/load.js
 *
 * TARGET_VUS: default 500. K6_DIRECT_APP + run.py cannot sustain 500 VUs — use Docker + :8080.
 *
 * End-of-test: summaryMode full. Redis: resolve_x_cache_HIT / resolve_x_cache_MISS in TOTAL RESULTS.
 */
function defaultBaseUrl() {
  if (__ENV.K6_IN_DOCKER === "1") {
    return "http://host.docker.internal:8080";
  }
  return "http://127.0.0.1:8080";
}

const BASE_URL = (__ENV.BASE_URL || defaultBaseUrl()).replace(/\/$/, "");
const DIRECT_APP = __ENV.K6_DIRECT_APP === "1";
const TARGET_VUS = parseInt(__ENV.TARGET_VUS || "500", 10);
const MIXED_WORKLOAD = __ENV.K6_MIXED_WORKLOAD === "1";
/** Extra pacing only for direct run.py at low VU counts (optional). */
const DIRECT_PACE = DIRECT_APP && TARGET_VUS <= 50;
const SEED_ALIAS = "k6hot";
const HIT_LB = BASE_URL.includes(":8080");

const reqParams = {
  timeout: "45s",
  headers: { Connection: "keep-alive" },
};

function postJson(url, body) {
  return http.post(url, body, {
    timeout: reqParams.timeout,
    headers: {
      ...reqParams.headers,
      "Content-Type": "application/json",
    },
  });
}

function headerGet(res, name) {
  if (!res || res.headers === undefined || res.headers === null) return "";
  const want = name.toLowerCase();
  const h = res.headers;

  const coerce = (v) => {
    if (v === undefined || v === null) return "";
    if (Array.isArray(v)) v = v[0];
    return String(v).trim();
  };

  for (const key of [name, name.toLowerCase(), name.toUpperCase()]) {
    if (Object.prototype.hasOwnProperty.call(h, key)) {
      const t = coerce(h[key]);
      if (t !== "") return t;
    }
  }
  for (const k in h) {
    if (Object.prototype.hasOwnProperty.call(h, k) && k.toLowerCase() === want) {
      return coerce(h[k]);
    }
  }
  const keys = Object.keys(h);
  for (let i = 0; i < keys.length; i++) {
    const k = keys[i];
    if (k.toLowerCase() === want) return coerce(h[k]);
  }
  return "";
}

function cacheLabel(res) {
  const a = headerGet(res, "X-Cache").toUpperCase();
  const b = headerGet(res, "X-Cache-Status").toUpperCase();
  return a || b;
}

function isCacheHitOrMiss(res) {
  const v = cacheLabel(res);
  return v === "HIT" || v === "MISS";
}

function isRedirectStatus(code) {
  return code === 301 || code === 302 || code === 303 || code === 307 || code === 308;
}

/** K6_DIRECT_APP + many VUs → macOS often hits ephemeral port exhaustion. */
const RELAX_THRESHOLDS = DIRECT_APP && TARGET_VUS >= 100;

export const options = {
  summaryMode: "full",
  discardResponseBodies: true,
  stages: [
    { duration: "15s", target: TARGET_VUS },
    { duration: "40s", target: TARGET_VUS },
    { duration: "10s", target: 0 },
  ],
  thresholds: RELAX_THRESHOLDS
    ? {
        http_req_failed: ["rate<0.45"],
        http_req_duration: ["p(95)<5000"],
        checks: ["rate>0.55"],
      }
    : {
        http_req_failed: ["rate<0.01"],
        http_req_duration: ["p(95)<5000"],
        checks: ["rate==1"],
      },
};

export function setup() {
  if (RELAX_THRESHOLDS) {
    console.warn(
      "K6_DIRECT_APP with TARGET_VUS>=100: k6 on Mac often gets 'can't assign requested address' " +
        "(ephemeral ports). For strict thresholds + 500 VUs use: docker compose up --build && k6 run k6/load.js"
    );
  }
  if (!DIRECT_APP && !BASE_URL.includes(":8080")) {
    throw new Error(
      "k6: BASE_URL must hit nginx on port :8080 (not :5000/:5001).\n" +
        "  On host:  k6 run k6/load.js  or  BASE_URL=http://127.0.0.1:8080 k6 run k6/load.js\n" +
        "  In grafana/k6 container:  -e K6_IN_DOCKER=1  or  -e BASE_URL=http://host.docker.internal:8080\n" +
        "  Linux Docker: add  --add-host=host.docker.internal:host-gateway\n" +
        "  Skip LB (debug):  K6_DIRECT_APP=1 BASE_URL=http://127.0.0.1:5000  (uv run run.py first)"
    );
  }

  const health = http.get(`${BASE_URL}/health`, reqParams);
  if (health.status !== 200) {
    if (health.status === 0) {
      if (DIRECT_APP) {
        throw new Error(
          `k6 setup: connection refused for ${BASE_URL}/health — start Flask or fix BASE_URL.`
        );
      }
      throw new Error(
        `k6 setup: connection refused for ${BASE_URL}/health. Start stack: docker compose up --build`
      );
    }
    throw new Error(
      `k6 setup: GET ${BASE_URL}/health → HTTP ${health.status}. Run: docker compose up --build`
    );
  }
  if (HIT_LB) {
    const lb = headerGet(health, "X-LB");
    if (!lb.toLowerCase().includes("nginx")) {
      throw new Error(
        "k6 setup: expected X-LB: nginx from load balancer on :8080. " +
          "Are you using BASE_URL=http://127.0.0.1:8080?"
      );
    }
  }

  const seedPayload = JSON.stringify({
    url: "https://loadtest.seed.example/k6-warm-alias",
    custom_alias: SEED_ALIAS,
  });
  const seed = postJson(`${BASE_URL}/shorten`, seedPayload);
  if (seed.status !== 201 && seed.status !== 200) {
    throw new Error(
      `k6 setup: seed shorten → ${seed.status} body=${String(seed.body).slice(0, 200)}`
    );
  }

  const p1 = { redirects: 0, ...reqParams };
  http.get(`${BASE_URL}/${SEED_ALIAS}`, p1);
  const warm2 = http.get(`${BASE_URL}/${SEED_ALIAS}`, p1);
  if (!isRedirectStatus(warm2.status)) {
    throw new Error(
      `k6 setup: GET /${SEED_ALIAS} expected redirect, got ${warm2.status}. Link resolve broken?`
    );
  }
  const label = cacheLabel(warm2);
  if (label !== "HIT") {
    throw new Error(
      `k6 setup: 2nd GET /${SEED_ALIAS} should be Redis cache HIT (got X-Cache=${label || "empty"}). ` +
        `Ensure REDIS_URL points at Redis for run.py.`
    );
  }

  return { alias: SEED_ALIAS };
}

function runResolveOnly(data) {
  const alias = data.alias;
  const p = { ...reqParams };
  const resolve = http.get(`${BASE_URL}/${alias}`, { redirects: 0, ...p });
  const redir = isRedirectStatus(resolve.status);
  const loc = headerGet(resolve, "Location");
  const lb = headerGet(resolve, "X-LB");

  check(resolve, {
    [`resolve ok (redirect, Location, X-Cache${HIT_LB ? ", X-LB" : ""})`]: () =>
      redir &&
      loc.length > 0 &&
      isCacheHitOrMiss(resolve) &&
      (!HIT_LB || lb.toLowerCase().includes("nginx")),
  });
  if (redir && loc.length > 0) {
    const lab = cacheLabel(resolve);
    if (lab === "HIT") resolveCacheHit.add(1);
    else if (lab === "MISS") resolveCacheMiss.add(1);
  }
  if (DIRECT_PACE) sleep(0.15);
}

function runMixedWorkload(data) {
  const alias = data.alias;
  const roll = Math.random();
  const p = { ...reqParams };

  if (roll < 0.03) {
    const health = http.get(`${BASE_URL}/health`, p);
    check(health, { "health 200": (r) => r.status === 200 });
    if (DIRECT_PACE) sleep(0.15);
    return;
  }

  if (roll < 0.95) {
    runResolveOnly(data);
    return;
  }

  const payload = JSON.stringify({
    url: `https://loadtest.example.com/vu-${__VU}-iter-${__ITER}-${Date.now()}`,
  });
  const shorten = postJson(`${BASE_URL}/shorten`, payload);
  check(shorten, {
    "shorten 201 or 200": (r) => r.status === 201 || r.status === 200,
  });
  if (DIRECT_PACE) sleep(0.15);
}

export default function (data) {
  if (MIXED_WORKLOAD) {
    runMixedWorkload(data);
  } else {
    runResolveOnly(data);
  }
}
