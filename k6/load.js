/**
 * 50 concurrent VUs (ramp → hold → ramp down).
 *
 * App with debug off:
 *   FLASK_DEBUG=false uv run run.py
 *
 * k6 (local):
 *   BASE_URL=http://127.0.0.1:5000 k6 run k6/load.js
 *
 * k6 (Docker on Mac, app on host):
 *   docker run --rm -i -v "$PWD/k6:/k6" -e BASE_URL=http://host.docker.internal:5000 grafana/k6 run /k6/load.js
 */
import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = (__ENV.BASE_URL || "http://127.0.0.1:5000").replace(/\/$/, "");

export const options = {
  stages: [
    { duration: "30s", target: 50 },
    { duration: "2m", target: 50 },
    { duration: "30s", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.1"],
    http_req_duration: ["p(95)<5000"],
  },
};

export default function () {
  const health = http.get(`${BASE_URL}/health`);
  check(health, { "health 200": (r) => r.status === 200 });

  const payload = JSON.stringify({
    url: `https://loadtest.example.com/vu-${__VU}-iter-${__ITER}-${Date.now()}`,
  });
  const shorten = http.post(`${BASE_URL}/shorten`, payload, {
    headers: { "Content-Type": "application/json" },
  });
  check(shorten, {
    "shorten 201 or 200": (r) => r.status === 201 || r.status === 200,
  });

  sleep(0.5);
}
