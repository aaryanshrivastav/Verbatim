// Stub: Redis Failure Scenario
// Cache unavailable test (manual: docker-compose stop redis)

import http from 'k6/http';
import { check } from 'k6';
import * as helpers from '../modules/helpers.js';

export const options = {
  vus: 10,
  duration: '2m',
};

export default function () {
  const products = helpers.listProducts();
  check(products, {
    'products still retrieved (degraded performance)': (p) => Array.isArray(p) && p.length > 0,
  });
}
