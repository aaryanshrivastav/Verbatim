// Environment Configuration
// Maps gateway and service URLs by deployment environment

export const environments = {
  // Docker Compose: All services accessible via localhost:8000 (main app aggregates all routers)
  docker: {
    gatewayUrl: 'http://localhost:8000',
    baseUrl: 'http://localhost:8000',
    auth: 'http://localhost:8000/auth',
    catalog: 'http://localhost:8000/products',
    orders: 'http://localhost:8000/orders',
    payment: 'http://localhost:8000/charge',
  },
  
  // Local development: Services on individual ports 8001-8004
  local: {
    gatewayUrl: 'http://localhost:8000',  // Gateway aggregates
    baseUrl: 'http://localhost:8000',      // Use gateway (not individual service ports)\n    auth: 'http://localhost:8001/auth',
    catalog: 'http://localhost:8002/products',
    orders: 'http://localhost:8003/orders',
    payment: 'http://localhost:8004/charge',
  },
  
  // Cloud deployments with remote gateway
  staging: {
    gatewayUrl: 'https://staging-api.example.com',
    baseUrl: 'https://staging-api.example.com',
    auth: 'https://staging-api.example.com/auth',
    catalog: 'https://staging-api.example.com/products',
    orders: 'https://staging-api.example.com/orders',
    payment: 'https://staging-api.example.com/charge',
  },
  
  production: {
    gatewayUrl: 'https://api.example.com',
    baseUrl: 'https://api.example.com',
    auth: 'https://api.example.com/auth',
    catalog: 'https://api.example.com/products',
    orders: 'https://api.example.com/orders',
    payment: 'https://api.example.com/charge',
  },
};

/**\n * Get environment config by name or from __ENV variable\n * Default: docker (for docker-compose up)\n */\nexport function getEnvironment() {\n  const env = __ENV.ENV || 'docker';\n  return environments[env] || environments.docker;\n}\n\nexport default getEnvironment();
