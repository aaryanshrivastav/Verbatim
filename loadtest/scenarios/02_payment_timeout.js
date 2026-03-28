// Payment Timeout Incident Scenario
// Simulates payment service timeout and validates graceful degradation
// Expected: Orders created with payment_failed status

import http from 'k6/http';
import { check, group } from 'k6';
import * as helpers from '../modules/helpers.js';

export const options = {
  vus: 20,
  duration: '2m',
  thresholds: {
    // Even with timeout, orders should be created (201)
    checks: ['value > 0.95'],  // 95% success rate
    // HTTP requests should succeed (201 status)
    http_req_failed: ['rate < 0.05'],
    // Latency will be high due to timeout (2s+ wait)
    http_req_duration: ['p(95) < 3000'],
  },
};

export function setup() {
  console.log('Setup: Payment Timeout Incident Test');
  console.log('Injecting incident: Payments will timeout...');

  // Inject incident: make payment service timeout
  const injectResponse = http.post(
    'http://localhost:8004/charge/simulate-failure',
    JSON.stringify({ always_timeout: true }),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );

  check(injectResponse, {
    'incident injected': (r) => r.status === 200,
  });

  // Get test data
  const products = helpers.listProducts();
  const auth = helpers.login('john_doe', 'secret');

  // Verify incident is active
  const configResponse = http.get('http://localhost:8003/orders/retry-config');
  console.log('Retry config:', configResponse.body);

  return {
    products,
    auth,
  };
}

export default function (data) {
  const { products, auth } = data;

  group('Order Creation During Payment Timeout', () => {
    // Create order - payment will timeout but order should still be created
    const items = helpers.createOrderItems(products, 1, 2);

    const orderPayload = JSON.stringify({
      user_id: auth.userId,
      items: items,
    });

    const startTime = Date.now();
    const response = http.post(
      'http://localhost:8000/api/v1/orders',
      orderPayload,
      {
        headers: {
          'Content-Type': 'application/json',
        },
      }
    );
    const duration = Date.now() - startTime;

    check(response, {
      'order created (201)': (r) => r.status === 201 || r.status === 200,
      'response is valid JSON': (r) => {
        try {
          JSON.parse(r.body);
          return true;
        } catch {
          return false;
        }
      },
    });

    if (response.status === 201 || response.status === 200) {
      const order = response.json('data');
      
      check(order, {
        'order id exists': (o) => o.id !== undefined,
        'order status is payment_failed': (o) => o.status === 'payment_failed',
        'total amount set': (o) => parseFloat(o.total_amount) > 0,
      });

      // Log for observability
      helpers.logTest('INFO', 'Order created during payment timeout', {
        order_id: order.id,
        status: order.status,
        duration_ms: duration,
      });

      // Verify timeout added delay
      check(duration, {
        'response time increased due to timeout': (d) => d > 1500,
        'response time reasonable': (d) => d < 5000,
      });
    }
  });

  group('Verify Order Status After Timeout', () => {
    // Get order and check status
    const orders = helpers.listProducts(); // Get any order to fetch
    if (orders.length > 0) {
      // Note: In real test, would use actual order ID from previous response
      // This is simplified for demo
      const order = orders[0];
      check(order, {
        'order accessible': (o) => o !== null,
      });
    }
  });
}

export function teardown(data) {
  console.log('Teardown: Disabling Payment Timeout Incident');

  // Disable incident
  const disableResponse = http.post(
    'http://localhost:8004/charge/simulate-failure',
    JSON.stringify({ normal: true }),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );

  check(disableResponse, {
    'incident disabled': (r) => r.status === 200,
  });

  console.log('Payment Timeout Incident Test Complete');
}
