import http from "k6/http";
import { check, sleep } from "k6";

// Change: Defaulting to Port 80 (the Load Balancer) instead of 5000 (the App)
const BASE_URL = (__ENV.BASE_URL || "http://127.0.0.1").replace(/\/$/, "");

export const options = {
  stages: [
    { duration: "30s", target: 50 }, // Ramp up to 50 users
    { duration: "2m", target: 50 },  // Stay at 50 users (The "Stress" phase)
    { duration: "30s", target: 0 },  // Ramp down
  ],
  thresholds: {
    // If more than 10% of requests fail, the test fails
    http_req_failed: ["rate<0.1"],
    // 95% of requests must complete under 5 seconds
    http_req_duration: ["p(95)<5000"],
  },
};

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

  // Wait 0.5 seconds before the next loop to simulate a "thinking" human
  sleep(0.5);
}