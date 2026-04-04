import http from "k6/http";
import { check, sleep } from "k6";

// Default :5000 = uv run / gunicorn on host. Docker Compose nginx on :80 → BASE_URL=http://127.0.0.1
const BASE_URL = (__ENV.BASE_URL || "http://127.0.0.1:5000").replace(/\/$/, "");

// TARGET_VUS from env, default 500. Example: TARGET_VUS=50 k6 run k6/load.js
const TARGET_VUS = parseInt(__ENV.TARGET_VUS || "500", 10);

export const options = {
  stages: [
    { duration: "60s", target: TARGET_VUS },
    { duration: "2m", target: TARGET_VUS },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    // If more than 10% of requests fail, the test fails
    http_req_failed: ["rate<0.1"],
    // 95% of requests must complete under 5 seconds
    http_req_duration: ["p(95)<5000"],
  },
};

/** One request before the test; fails fast with a clear message if BASE_URL is wrong. */
export function setup() {
  const res = http.get(`${BASE_URL}/health`);
  if (res.status !== 200) {
    const hint =
      res.status === 0
        ? " (connection failed — wrong port or server not running)"
        : "";
    throw new Error(
      `k6 setup: GET ${BASE_URL}/health → status ${res.status}${hint}. ` +
        `Use BASE_URL=http://127.0.0.1:5000 for uv run / gunicorn on host, ` +
        `or BASE_URL=http://127.0.0.1 after docker compose up (nginx :80).`
    );
  }
}

export default function () {
  // 1. Check Health
  const health = http.get(`${BASE_URL}/health`);
  check(health, { "health 200": (r) => r.status === 200 });

  // 2. Create a Short Link
  // We use the VU and Iteration number to make every URL unique
  const payload = JSON.stringify({
    url: `https://loadtest.example.com/vu-${__VU}-iter-${__ITER}-${Date.now()}`,
  });

  const shorten = http.post(`${BASE_URL}/shorten`, payload, {
    headers: { "Content-Type": "application/json" },
  });

  check(shorten, {
    "shorten 201 or 200": (r) => r.status === 201 || r.status === 200,
  });

}