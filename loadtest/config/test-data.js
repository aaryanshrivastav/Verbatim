// Test Data Configuration
// Seeded users and products for testing

export const testUsers = [
  {
    username: 'john_doe',
    password: 'secret',
    userId: undefined, // Fetched at runtime
  },
  {
    username: 'jane_smith',
    password: 'secret',
    userId: undefined,
  },
];

export const testProducts = [
  {
    name: 'Laptop',
    price: 1299.99,
    id: undefined, // Fetched at runtime
  },
  {
    name: 'Monitor',
    price: 599.99,
    id: undefined,
  },
  {
    name: 'Keyboard',
    price: 199.99,
    id: undefined,
  },
  {
    name: 'Mouse',
    price: 49.99,
    id: undefined,
  },
];

export async function loadTestData() {
  return {
    users: testUsers,
    products: testProducts,
  };
}

export default {
  testUsers,
  testProducts,
  loadTestData,
};
