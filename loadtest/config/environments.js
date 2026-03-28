// Environment Configuration
// Different URLs for dev, staging, production

export const environments = {
  local: {
    gatewayUrl: 'http://localhost:8000',
    apiPrefix: '/api/v1',
    authServiceUrl: 'http://localhost:8001',
    catalogServiceUrl: 'http://localhost:8002',
    orderServiceUrl: 'http://localhost:8003',
    paymentServiceUrl: 'http://localhost:8004',
  },
  staging: {
    gatewayUrl: 'https://staging-gateway.example.com',
    apiPrefix: '/api/v1',
    authServiceUrl: 'https://staging-auth.example.com',
    catalogServiceUrl: 'https://staging-catalog.example.com',
    orderServiceUrl: 'https://staging-order.example.com',
    paymentServiceUrl: 'https://staging-payment.example.com',
  },
  production: {
    gatewayUrl: 'https://api.example.com',
    apiPrefix: '/api/v1',
    authServiceUrl: 'https://auth.example.com',
    catalogServiceUrl: 'https://catalog.example.com',
    orderServiceUrl: 'https://order.example.com',
    paymentServiceUrl: 'https://payment.example.com',
  },
};

/**
 * Get environment config by name or from __ENV variable
 */
export function getEnvironment() {
  const env = __ENV.ENVIRONMENT || 'local';
  return environments[env] || environments.local;
}

export default getEnvironment();
