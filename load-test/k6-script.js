import http from 'k6/http';
import { sleep, check } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const errorRate   = new Rate('error_rate');
const apiLatency  = new Trend('api_latency_ms', true);

const BASE_URL = __ENV.BASE_URL || 'http://app.localhost';

export const options = {
  stages: [
    { duration: '30s', target: 20  }, // ramp up
    { duration: '5m',  target: 20  }, // steady state (chaos experiments qui)
    { duration: '30s', target: 0   }, // ramp down
  ],
  thresholds: {
    http_req_failed:   ['rate<0.05'],   // < 5% error rate
    http_req_duration: ['p(95)<800'],   // p95 < 800ms
  },
};

export default function () {
  // GET /api/items
  const listRes = http.get(`${BASE_URL}/api/items`, {
    tags: { endpoint: 'list_items' },
  });

  check(listRes, {
    'list items status 200': r => r.status === 200,
    'list items has body':   r => r.body && r.body.length > 0,
  });
  errorRate.add(listRes.status >= 500);
  apiLatency.add(listRes.timings.duration);

  sleep(0.5);

  // POST /api/items
  const payload = JSON.stringify({
    name:        `item-${Date.now()}`,
    description: 'Generato da k6 load test',
    price:       Math.round(Math.random() * 100 * 100) / 100,
  });

  const createRes = http.post(`${BASE_URL}/api/items`, payload, {
    headers: { 'Content-Type': 'application/json' },
    tags: { endpoint: 'create_item' },
  });

  check(createRes, {
    'create item status 201': r => r.status === 201,
  });
  errorRate.add(createRes.status >= 500);

  sleep(0.5);

  // GET /health
  const healthRes = http.get(`${BASE_URL}/health`, {
    tags: { endpoint: 'health' },
  });

  check(healthRes, {
    'health ok': r => r.status === 200,
  });

  sleep(0.5);
}
