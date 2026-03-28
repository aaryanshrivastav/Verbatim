// Mixed Traffic Scenario
// Realistic blend of different user behaviors

import http from 'k6/http';
import { check, group } from 'k6';
import { randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';
import * as helpers from '../modules/helpers.js';

export const options = {
  vus: 30,
  duration: '5m',
  thresholds: {
    checks: ['rate > 0.95'],
    http_req_failed: ['rate < 0.05'],
  },
};

export function setup() {
  return {
    products: helpers.listProducts(),
  };
}

export default function (data) {
  const { products } = data;
  const behavior = randomIntBetween(1, 100);

  if (behavior <= 40) {
    // 40% - Browse only
    group('Browse Products Only', () => {
      helpers.listProducts();
      if (products.length > 0) {
        helpers.getProduct(products[0].id);
      }
    });
  } else if (behavior <= 90) {
    // 50% - Full checkout
    group('Full Checkout', () => {
      const auth = helpers.login('john_doe', 'secret');
      if (auth) {
        helpers.validateToken(auth.token);
        const items = helpers.createOrderItems(products, 1, 3);
        helpers.createOrder(auth.userId, items);
      }
    });
  } else if (behavior <= 95) {
    // 5% - Failed login
    group('Failed Login Attempt', () => {
      const response = http.post(
        'http://localhost:8000/api/v1/auth/login',
        JSON.stringify({ username: 'john_doe', password: 'wrong' }),
        { headers: { 'Content-Type': 'application/json' } }
      );
      check(response, { 'unauthorized': (r) => r.status === 401 });
    });
  } else {
    // 5% - Invalid product request
    group('Invalid Product Request', () => {
      const response = http.get('http://localhost:8000/api/v1/products/invalid-id');
      check(response, { 'bad request': (r) => r.status === 400 });
    });
  }
}
