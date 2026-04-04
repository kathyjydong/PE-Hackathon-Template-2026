import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 50,
  duration: '30s',
};

export default function () {
  const res = http.get('http://127.0.0.1:5000/health');
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(1);
}
