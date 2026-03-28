// Stub: Service Down Scenario
// Test when payment service is unavailable

import http from 'k6/http';
import { check, group } from 'k6';
import * as helpers from '../modules/helpers.js';

export const options = {
  vus: 10,
  duration: '1m',
};

export function setup() {
  console.log('Note: Manually stop payment service before running this test');
  const products = helpers.listProducts();
  const auth = helpers.login('john_doe', 'secret');
  return { products, auth };
}

export default function (data) {
  const { products, auth } = data;

  group('Order Creation With Service Down', () => {
    const items = helpers.createOrderItems(products, 1, 1);
    const response = http.post(
      'http://localhost:8000/api/v1/orders',
      JSON.stringify({ user_id: auth.userId, items }),
      { headers: { 'Content-Type': 'application/json' } }
    );

    check(response, {
      'returns error (503 or timeout)': (r) => r.status >= 500 || r.status === 0,
    });
  });
}

export function teardown() {
  console.log('Note: Manual restart of payment service required');
}
