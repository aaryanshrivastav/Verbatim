// Helper Functions for k6 Tests
// Common utilities for all test scenarios

import http from 'k6/http';
import { check, group } from 'k6';
import { randomString, randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

/**
 * Extract test data from gateway responses
 */
export function extractProductIds() {
  const response = http.get('http://localhost:8000/api/v1/products');
  check(response, {
    'products retrieved': (r) => r.status === 200,
  });
  
  if (response.status === 200) {
    const products = response.json('data');
    if (Array.isArray(products)) {
      return products.map(p => p.id);
    }
  }
  return [];
}

/**
 * Login and get token for authenticated requests
 */
export function login(username = 'john_doe', password = 'secret') {
  const payload = JSON.stringify({
    username: username,
    password: password,
  });

  const response = http.post(
    'http://localhost:8000/api/v1/auth/login',
    payload,
    {
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  check(response, {
    'login successful': (r) => r.status === 200,
  });

  if (response.status === 200) {
    const body = response.json('data');
    return {
      token: body.token,
      userId: body.user_id,
    };
  }
  return null;
}

/**
 * Validate token
 */
export function validateToken(token) {
  const payload = JSON.stringify({ token: token });

  const response = http.post(
    'http://localhost:8000/api/v1/auth/validate',
    payload,
    {
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  check(response, {
    'token validation returned 200': (r) => r.status === 200,
  });

  return response.json('data');
}

/**
 * Create order with given items and user ID
 */
export function createOrder(userId, items) {
  const payload = JSON.stringify({
    user_id: userId,
    items: items,
  });

  const response = http.post(
    'http://localhost:8000/api/v1/orders',
    payload,
    {
      headers: {
        'Content-Type': 'application/json',
      },
    }
  );

  check(response, {
    'order created': (r) => r.status === 201 || r.status === 200,
  });

  if (response.status === 201 || response.status === 200) {
    const order = response.json('data');
    return {
      orderId: order.id,
      status: order.status,
      totalAmount: order.total_amount,
    };
  }
  return null;
}

/**
 * Get order details
 */
export function getOrder(orderId) {
  const response = http.get(`http://localhost:8000/api/v1/orders/${orderId}`);

  check(response, {
    'order retrieved': (r) => r.status === 200,
  });

  if (response.status === 200) {
    return response.json('data');
  }
  return null;
}

/**
 * List all products
 */
export function listProducts() {
  const response = http.get('http://localhost:8000/api/v1/products');

  check(response, {
    'products listed': (r) => r.status === 200,
  });

  if (response.status === 200) {
    return response.json('data');
  }
  return [];
}

/**
 * Get single product
 */
export function getProduct(productId) {
  const response = http.get(`http://localhost:8000/api/v1/products/${productId}`);

  check(response, {
    'product retrieved': (r) => r.status === 200,
  });

  if (response.status === 200) {
    return response.json('data');
  }
  return null;
}

/**
 * Health check for services
 */
export function healthCheck() {
  const response = http.get('http://localhost:8000/health');
  return response.json();
}

/**
 * Get metrics from Prometheus endpoint
 */
export function getMetrics() {
  const response = http.get('http://localhost:8000/metrics');
  return response.body;
}

/**
 * Create test order items (random selection from products)
 */
export function createOrderItems(products, minItems = 1, maxItems = 3) {
  const itemCount = randomIntBetween(minItems, maxItems);
  const items = [];

  for (let i = 0; i < itemCount; i++) {
    const product = products[randomIntBetween(0, products.length - 1)];
    const quantity = randomIntBetween(1, 5);

    items.push({
      product_id: product.id,
      quantity: quantity,
    });
  }

  return items;
}

/**
 * Measure operation latency
 */
export function measureLatency(label, fn) {
  const startTime = Date.now();
  const result = fn();
  const duration = Date.now() - startTime;

  console.log(`${label}: ${duration}ms`);
  return { result, duration };
}

/**
 * Retry operation with exponential backoff
 */
export function retryWithBackoff(fn, maxAttempts = 3, initialDelayMs = 100) {
  let lastError;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      return fn();
    } catch (e) {
      lastError = e;
      const delayMs = initialDelayMs * Math.pow(2, attempt);
      console.log(`Attempt ${attempt + 1} failed, retrying in ${delayMs}ms...`);
      // k6 doesn't have sleep, but would be: sleep(delayMs / 1000)
    }
  }

  throw lastError;
}

/**
 * Validate response structure
 */
export function validateOrderResponse(order) {
  check(order, {
    'has order id': (o) => o.id !== undefined && o.id !== null,
    'has user id': (o) => o.user_id !== undefined,
    'has total amount': (o) => o.total_amount !== undefined,
    'has status': (o) => o.status !== undefined,
    'has items': (o) => Array.isArray(o.items),
  });
}

/**
 * Validate product response
 */
export function validateProductResponse(product) {
  check(product, {
    'has id': (p) => p.id !== undefined,
    'has name': (p) => p.name !== undefined,
    'has price': (p) => p.price !== undefined,
    'has stock_quantity': (p) => p.stock_quantity !== undefined,
  });
}

/**
 * Get request headers with tracing context
 */
export function getTracingHeaders() {
  // Generate trace IDs for manual tracing
  const traceId = randomString(32);
  const spanId = randomString(16);

  return {
    'Content-Type': 'application/json',
    'traceparent': `00-${traceId}-${spanId}-01`,
    'tracestate': 'microservices-demo',
  };
}

/**
 * Log structured message
 */
export function logTest(level, message, data = {}) {
  const timestamp = new Date().toISOString();
  console.log(JSON.stringify({
    timestamp,
    level,
    message,
    ...data,
  }));
}

export default {
  extractProductIds,
  login,
  validateToken,
  createOrder,
  getOrder,
  listProducts,
  getProduct,
  healthCheck,
  getMetrics,
  createOrderItems,
  measureLatency,
  retryWithBackoff,
  validateOrderResponse,
  validateProductResponse,
  getTracingHeaders,
  logTest,
};
