import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";

/** Count X-Cache on successful redirects (verify Redis after warmup) */
const resolveCacheHit = new Counter("resolve_x_cache_HIT");
const resolveCacheMiss = new Counter("resolve_x_cache_MISS");

// 1. UPDATED: Pointing directly to your production Droplet
function defaultBaseUrl() {
  return "https://short.urlshortener-mlh.xyz";
}

const BASE_URL = (__ENV.BASE_URL || defaultBaseUrl()).replace(/\/$/, "");
const DIRECT_APP = __ENV.K6_DIRECT_APP === "1";
const TARGET_VUS = parseInt(__ENV.TARGET_VUS || "500", 10);
const MIXED_WORKLOAD = __ENV.K6_MIXED_WORKLOAD === "1";
const DIRECT_PACE = DIRECT_APP && TARGET_VUS <= 50;
const SEED_ALIAS = "k6hot";

// 2. UPDATED: Turned off local load balancer header checks
const HIT_LB = false; 

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

const RELAX_THRESHOLDS = DIRECT_APP && TARGET_VUS >= 100;

export const options = {
  summaryMode: "full",
  discardResponseBodies: true,
  stages: [
    { duration: "30s", target: TARGET_VUS },
    { duration: "2m", target: TARGET_VUS },
    { duration: "30s", target: 0 },
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
  // 3. UPDATED: Removed the crash-inducing local :8080 guardrail

  const health = http.get(`${BASE_URL}/health`, reqParams);
  if (health.status !== 200) {
    throw new Error(
      `k6 setup: GET ${BASE_URL}/health → HTTP ${health.status}. Is the production server running?`
    );
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
    console.warn(`k6 setup warning: Expected Redis HIT, got ${label || "empty"}. Proceeding anyway.`);
  }

  return { alias: SEED_ALIAS };
}

function runResolveOnly(data) {
  const alias = data.alias;
  const p = { ...reqParams };
  const resolve = http.get(`${BASE_URL}/${alias}`, { redirects: 0, ...p });
  const redir = isRedirectStatus(resolve.status);
  const loc = headerGet(resolve, "Location");

  check(resolve, {
    "resolve ok (redirect, Location, X-Cache)": () =>
      redir && loc.length > 0 && isCacheHitOrMiss(resolve),
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