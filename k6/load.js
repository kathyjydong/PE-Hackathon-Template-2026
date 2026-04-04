import http from "k6/http";
import { check } from "k6";

/**
 * Do NOT set BASE_URL=http://127.0.0.1:5000 — that bypasses nginx; setup will fail on purpose.
 *
 * Correct (through load balancer + Redis checks):
 *   docker compose up --build
 *   k6 run k6/load.js
 *
 * Direct gunicorn only (no LB / no X-LB check — use mapped host port, often 5001 on Mac):
 *   K6_DIRECT_APP=1 BASE_URL=http://127.0.0.1:5001 k6 run k6/load.js
 *
 * Optional: TARGET_VUS=500 (default). Lighter: TARGET_VUS=200 k6 run k6/load.js
 */
const BASE_URL = (__ENV.BASE_URL || "http://127.0.0.1:8080").replace(/\/$/, "");
const TARGET_VUS = parseInt(__ENV.TARGET_VUS || "500", 10);
const SEED_ALIAS = "k6hot";
const DIRECT_APP = __ENV.K6_DIRECT_APP === "1";
const HIT_LB = BASE_URL.includes(":8080");

const reqParams = {
  timeout: "45s",
};

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

export const options = {
  stages: [
    { duration: "15s", target: TARGET_VUS },
    { duration: "40s", target: TARGET_VUS },
    { duration: "10s", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.05"],
    http_req_duration: ["p(95)<5000"],
  },
};

export function setup() {
  if (!DIRECT_APP && !BASE_URL.includes(":8080")) {
    throw new Error(
      "k6: BASE_URL must use nginx on :8080 (load balancer), not :5000/:5001.\n" +
        "  Fix: unset BASE_URL and run:  k6 run k6/load.js\n" +
        "   Or: BASE_URL=http://127.0.0.1:8080 k6 run k6/load.js\n" +
        "  Skip LB (debug only):  K6_DIRECT_APP=1 BASE_URL=http://127.0.0.1:5001 k6 run k6/load.js"
    );
  }

  const health = http.get(`${BASE_URL}/health`, reqParams);
  if (health.status !== 200) {
    throw new Error(
      `k6 setup: GET ${BASE_URL}/health → ${health.status}. Run: docker compose up --build`
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
  const seed = http.post(`${BASE_URL}/shorten`, seedPayload, {
    headers: { "Content-Type": "application/json" },
    ...reqParams,
  });
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
      `k6 setup: 2nd GET /${SEED_ALIAS} should be Redis cache HIT (got X-Cache/X-Cache-Status=${label || "empty"}). ` +
        `Check app REDIS_URL and redis container.`
    );
  }

  return { alias: SEED_ALIAS };
}

export default function (data) {
  const alias = data.alias;
  const roll = Math.random();
  const p = { ...reqParams };

  // ~92% resolve (Redis after warmup), ~3% health, ~5% shorten — keeps Postgres and queue depth lower
  if (roll < 0.03) {
    const health = http.get(`${BASE_URL}/health`, p);
    check(health, { "health 200": (r) => r.status === 200 });
    return;
  }

  if (roll < 0.95) {
    const resolve = http.get(`${BASE_URL}/${alias}`, { redirects: 0, ...p });
    const redir = isRedirectStatus(resolve.status);
    const loc = headerGet(resolve, "Location");
    const lb = headerGet(resolve, "X-LB");

    check(resolve, {
      "resolve redirect (3xx)": () => redir,
    });
    if (redir) {
      const detail = {
        "resolve has Location": () => loc.length > 0,
        "redis cache header (HIT/MISS)": () => isCacheHitOrMiss(resolve),
      };
      if (HIT_LB) {
        detail["via nginx LB (X-LB)"] = () => lb.toLowerCase().includes("nginx");
      }
      check(resolve, detail);
    }
    return;
  }

  const payload = JSON.stringify({
    url: `https://loadtest.example.com/vu-${__VU}-iter-${__ITER}-${Date.now()}`,
  });
  const shorten = http.post(`${BASE_URL}/shorten`, payload, {
    headers: { "Content-Type": "application/json" },
    ...p,
  });
  check(shorten, {
    "shorten 201 or 200": (r) => r.status === 201 || r.status === 200,
  });
}
