// Stub: Database Exhaustion Scenario
// Connection pool exhaustion test

import http from 'k6/http';
import { check, group } from 'k6';
import * as helpers from '../modules/helpers.js';

export const options = {
  vus: 50,
  duration: '2m',
};

export function setup() {
  return { products: helpers.listProducts(), auth: helpers.login('john_doe', 'secret') };
}

export default function (data) {
  helpers.createOrder(data.auth.userId, helpers.createOrderItems(data.products, 1, 2));
}
