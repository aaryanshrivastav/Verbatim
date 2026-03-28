// DDoS / Load Spike Scenario
// Gradually ramp traffic to simulate sudden demand spike
// Validates system resilience and recovery

import http from 'k6/http';
import { check, group } from 'k6';
import * as helpers from '../modules/helpers.js';

export const options = {
  stages: [
    { duration: '2m', target: 50 },    // Ramp: 0 → 50 VUs
    { duration: '5m', target: 50 },    // Baseline: hold 50 VUs
    { duration: '2m', target: 200 },   // Spike: 50 → 200 VUs (4x)
    { duration: '5m', target: 200 },   // Sustain: hold 200 VUs
    { duration: '2m', target: 0 },     // Ramp down: 200 → 0
  ],
  thresholds: {
    checks: ['value > 0.85'],
    http_req_failed: ['rate < 0.10'],  // Allow up to 10% failures during spike
    http_req_duration: ['p(95) < 2000'],
  },
};

export function setup() {
  console.log('Setup: DDoS Load Spike Scenario');
  const products = helpers.listProducts();
  const auth = helpers.login('john_doe', 'secret');
  return { products, auth };
}

export default function (data) {
  const { products, auth } = data;

  group('Full Checkout Flow Under Load', () => {
    // List products
    helpers.listProducts();

    // Validate token
    helpers.validateToken(auth.token);

    // Create order
    const items = helpers.createOrderItems(products, 1, 3);
    const order = helpers.createOrder(auth.userId, items);

    if (order) {
      // Get order details
      helpers.getOrder(order.orderId);
    }
  });
}

export function teardown() {
  console.log('DDoS Load Spike Test Complete');
}
