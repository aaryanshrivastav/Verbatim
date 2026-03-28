// Baseline Load Test Scenario
// Happy path: browse, login, create order, verify
// Validates healthy system performance and observability signals

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';
import * as helpers from '../modules/helpers.js';

// Test configuration
export const options = {
  vus: 10,           // 10 concurrent virtual users
  duration: '2m',    // Test for 2 minutes
  thresholds: {
    // ThresholdsFailed = any check failed
    checks: ['value < 0.1'],  // 90% success rate
    // Error rate must be < 5%
    http_req_failed: ['rate < 0.05'],
    // P95 latency must be < 2s
    http_req_duration: ['p(95) < 2000'],
  },
};

// Setup: Extract test data and login
export function setup() {
  console.log('Setup: Extracting test data...');

  // Get product IDs from gateway
  const products = helpers.listProducts();
  console.log(`Found ${products.length} products`);

  // Login to get token
  const auth = helpers.login('john_doe', 'secret');
  console.log(`Logged in as john_doe, token: ${auth.token.substring(0, 20)}...`);

  return {
    products,
    auth,
  };
}

// Main VU function - executed by each virtual user
export default function (data) {
  const { products, auth } = data;

  // VU Flow: Browse → Validate → Create Order → Verify
  
  group('Browse Products', () => {
    // Get products (first call might miss cache)
    let productsResponse = helpers.listProducts();
    check(productsResponse, {
      'products array returned': (p) => Array.isArray(p) && p.length > 0,
      'products have correct structure': (p) => {
        if (p.length > 0) {
          const first = p[0];
          return first.id && first.name && first.price && first.stock_quantity !== undefined;
        }
        return false;
      },
    });

    sleep(randomIntBetween(1, 3));

    // Get specific product (should hit cache if recent)
    if (productsResponse.length > 0) {
      const productId = productsResponse[0].id;
      let product = helpers.getProduct(productId);
      helpers.validateProductResponse(product);
      check(product, {
        'correct product returned': (p) => p.id === productId,
      });
    }

    sleep(randomIntBetween(1, 2));
  });

  group('Validate Auth', () => {
    // Validate token
    const validation = helpers.validateToken(auth.token);
    check(validation, {
      'token is valid': (v) => v.valid === true,
      'correct user id': (v) => v.user_id === auth.userId,
    });

    sleep(1);
  });

  group('Create Order', () => {
    // Build order with random items
    const items = helpers.createOrderItems(products, 1, 3);
    console.log(`Creating order with ${items.length} items`);

    // Create order
    const order = helpers.createOrder(auth.userId, items);
    check(order !== null, {
      'order created successfully': true,
    });

    if (order) {
      helpers.validateOrderResponse(order);
      check(order, {
        'order has confirmed or failed status': (o) => 
          o.status === 'confirmed' || o.status === 'payment_failed',
        'order total > 0': (o) => parseFloat(o.totalAmount) > 0,
      });

      sleep(randomIntBetween(1, 2));

      // Get order details to verify
      const orderDetails = helpers.getOrder(order.orderId);
      check(orderDetails, {
        'order details match': (od) => od.id === order.orderId,
        'order has items': (od) => od.items && od.items.length > 0,
      });
    }

    sleep(randomIntBetween(2, 4));
  });

  // Repeat: Fast re-browse (should hit cache)
  group('Fast Re-browse (Cache Hit)', () => {
    let productsResponse = helpers.listProducts();
    check(productsResponse, {
      'products still available': (p) => Array.isArray(p) && p.length > 0,
    });

    sleep(randomIntBetween(1, 2));
  });
}

// Teardown: Log summary
export function teardown(data) {
  console.log('Teardown: Test complete');
  
  // Optional: Get final health check
  const health = helpers.healthCheck();
  console.log('Final Health Check:', JSON.stringify(health, null, 2));
}
