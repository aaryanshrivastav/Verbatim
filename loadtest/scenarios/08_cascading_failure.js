// Stub: Cascading Failure Scenario
// Multi-service cascade under retry pressure

import http from 'k6/http';
import { check } from 'k6';
import * as helpers from '../modules/helpers.js';

export const options = {
  stages: [
    { duration: '1m', target: 100 },
    { duration: '3m', target: 100 },
    { duration: '1m', target: 0 },
  ],
};

export function setup() {
  // Setup assumes ENABLE_RETRY_STORM=true and payment timeout injected
  return {
    products: helpers.listProducts(),
    auth: helpers.login('john_doe', 'secret'),
  };
}

export default function (data) {
  const response = http.post(
    'http://localhost:8000/api/v1/orders',
    JSON.stringify({
      user_id: data.auth.userId,
      items: helpers.createOrderItems(data.products, 1, 2),
    }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(response, {
    'response received': (r) => r.status !== 0,
  });
}
