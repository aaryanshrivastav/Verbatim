// Retry Storm Incident Scenario
// Payment failures trigger exponential backoff retries
// Expected: 3x payment attempts per order, 3000-3500ms latency

import http from 'k6/http';
import { check, group } from 'k6';
import * as helpers from '../modules/helpers.js';

export const options = {
  vus: 15,
  duration: '3m',
  thresholds: {
    checks: ['value > 0.90'],
    http_req_duration: ['p(95) < 4000'],  // Longer latency due to retries
  },
};

export function setup() {
  console.log('Setup: Retry Storm Incident Test');
  console.log('Enabling retry storm: MAX_RETRIES=3, exponential backoff enabled');

  // Note: In real scenario, ENABLE_RETRY_STORM would be set via env var
  // and services restarted. For this test, we simulate by:
  // 1. Injecting payment failures
  // 2. Relying on retry logic in order service
  
  // Inject payment failures to trigger retries
  const injectResponse = http.post(
    'http://localhost:8004/charge/simulate-failure',
    JSON.stringify({ always_fail: true }),  // Make all payments fail
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );

  check(injectResponse, {
    'failure mode injected': (r) => r.status === 200,
  });

  // Verify retry config
  const configResponse = http.get('http://localhost:8003/orders/retry-config');
  const config = configResponse.json();
  console.log('Retry configuration:', {
    retry_enabled: config.retry_enabled,
    max_retries: config.max_retries,
    initial_backoff_seconds: config.initial_backoff_seconds,
  });

  const products = helpers.listProducts();
  const auth = helpers.login('jane_smith', 'secret');  // Use different user

  return {
    products,
    auth,
  };
}

export default function (data) {
  const { products, auth } = data;

  group('Order Creation with Retry Storm', () => {
    const items = helpers.createOrderItems(products, 1, 2);

    // Create order - payment will fail and trigger retries
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
      'response received': (r) => r.status >= 200,
      'order endpoint responds': (r) => r.status !== 504,  // No gateway timeout
    });

    if (response.status === 201 || response.status === 200) {
      const order = response.json('data');

      // With retries and failures, order might end up in payment_failed status
      check(order, {
        'order created': (o) => o.id !== undefined,
        'status final': (o) => o.status === 'payment_failed' || o.status === 'confirmed',
      });

      // Key metric: latency should be 3000+ ms due to 3 retry attempts
      // Timeline:
      // t=0ms: DB writes
      // t=50ms: Retry 1 (fails)
      // t=50-1150ms: Backoff sleep
      // t=1150ms: Retry 2 (fails)
      // t=1150-3300ms: Backoff sleep
      // t=3300ms: Retry 3 (fails, max reached)
      // t=3300-3350ms: Status update
      
      helpers.logTest('INFO', 'Order created with retry storm', {
        order_id: order.id,
        status: order.status,
        duration_ms: duration,
        expected_min_duration: 3000,
      });

      check(duration, {
        'latency increased by retries (>3s)': (d) => d > 3000,
        'latency within reasonable bounds': (d) => d < 5000,
      });
    } else if (response.status === 400) {
      // Order might fail if user not found (different user scenario)
      check(response, {
        'error response structured': (r) => r.body.length > 0,
      });
    }
  });

  group('Health Check During Retry Storm', () => {
    const health = helpers.healthCheck();
    
    // During retry storm, system might be degraded
    // But should still respond (not returning 503 everywhere)
    check(health, {
      'health endpoint responds': (h) => h !== null,
    });
  });
}

export function teardown(data) {
  console.log('Teardown: Disabling Retry Storm');

  // Reset payment service to normal
  const resetResponse = http.post(
    'http://localhost:8004/charge/simulate-failure',
    JSON.stringify({ normal: true }),
    {
      headers: { 'Content-Type': 'application/json' },
    }
  );

  check(resetResponse, {
    'payment service reset': (r) => r.status === 200,
  });

  // In production scenario, would also:
  // export ENABLE_RETRY_STORM=false
  // docker-compose restart order

  console.log('Retry Storm Incident Test Complete');
}
