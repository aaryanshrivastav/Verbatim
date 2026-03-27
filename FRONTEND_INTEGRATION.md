"""Frontend Integration Guide"""

# Frontend Integration Guide

This guide explains how to integrate a frontend application with the Verbatim microservices.

## Architecture Overview

```
┌─────────────────┐
│    Frontend     │
│    (Entry)      │
└────────┬────────┘
         │
         ▼
    ┌─────────────────────────────────────────────┐
    │  API Gateway (/api/v1)                      │
    │  - Single Entry Point                       │
    │  - Request Routing & Validation             │
    └────────┬────────────────────────────────────┘
             │
    ┌────────┴─────────────────┬──────────────┐
    │                          │              │
    ▼                          ▼              ▼
┌─────────────┐        ┌──────────────┐  ┌──────────────┐
│Auth Service │        │Catalog       │  │Order Service │
│             │        │Service       │  │(with Payment)│
└─────────────┘        └──────────────┘  └────┬─────────┘
                                              │
                                              ▼
                                       ┌──────────────┐
                                       │Payment       │
                                       │Service       │
                                       └──────────────┘
                                              │
                ┌───────────────────────────┬─┘
                │                           │
                ▼                           ▼
         ┌──────────────┐          ┌──────────────┐
         │Shared DB     │          │Redis Cache   │
         └──────────────┘          └──────────────┘
```

## API Endpoints

All frontend requests go through the gateway at `/api/v1`.

### Base URL
```
http://localhost:8000/api/v1
```

### Available Endpoints

#### 1. Product Catalog

**List Products**
```http
GET /api/v1/products
```

Response:
```json
{
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Product 1",
      "price": "99.99",
      "stock": 100
    }
  ]
}
```

**Get Single Product**
```http
GET /api/v1/products/{product_id}
```

#### 2. Authentication

**Login**
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "testuser",
  "password": "password123"
}
```

Response:
```json
{
  "data": {
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "token": "secure_token_32bytes",
    "expires_at": "2026-03-29T12:00:00"
  }
}
```

**Validate Authentication**
```http
POST /api/v1/auth/validate
Content-Type: application/json

{
  "token": "secure_token_32bytes"
}
```

#### 3. Orders (Cart/Checkout)

**Create Order**
```http
POST /api/v1/orders
Content-Type: application/json

{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "items": [
    {
      "product_id": "660e8400-e29b-41d4-a716-446655441111",
      "quantity": 2
    },
    {
      "product_id": "770e8400-e29b-41d4-a716-446655442222",
      "quantity": 1
    }
  ]
}
```

Response:
```json
{
  "data": {
    "order_id": "880e8400-e29b-41d4-a716-446655443333",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "confirmed",
    "total_amount": "299.97",
    "items": [...],
    "created_at": "2026-03-28T12:00:00",
    "payment": {
      "status": "success",
      "method": "gateway"
    }
  }
}
```

**Get Order Status**
```http
GET /api/v1/orders/{order_id}
```

Response:
```json
{
  "data": {
    "order_id": "880e8400-e29b-41d4-a716-446655443333",
    "status": "confirmed",
    "total_amount": "299.97",
    "payment_status": "success"
  }
}
```

#### 4. Payment (Direct Access - Optional)

**Charge Payment** (Usually called automatically when creating order)
```http
POST /api/v1/charge
Content-Type: application/json

{
  "order_id": "880e8400-e29b-41d4-a716-446655443333",
  "amount": 299.97,
  "currency": "USD"
}
```

## Implementation Examples

### JavaScript/Fetch

```javascript
const API_BASE = 'http://localhost:8000/api/v1';

// 1. List Products
async function getProducts() {
  const response = await fetch(`${API_BASE}/products`);
  const { data } = await response.json();
  return data;
}

// 2. Get Single Product
async function getProduct(productId) {
  const response = await fetch(`${API_BASE}/products/${productId}`);
  const { data } = await response.json();
  return data;
}

// 3. Login
async function login(username, password) {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });
  const { data } = await response.json();
  localStorage.setItem('token', data.token);
  return data;
}

// 4. Validate Token
async function validateToken() {
  const token = localStorage.getItem('token');
  const response = await fetch(`${API_BASE}/auth/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token })
  });
  return response.ok;
}

// 5. Create Order
async function createOrder(userId, items) {
  const response = await fetch(`${API_BASE}/orders`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_id: userId,
      items: items
    })
  });
  const { data } = await response.json();
  return data;
}

// 6. Get Order Status
async function getOrderStatus(orderId) {
  const response = await fetch(`${API_BASE}/orders/${orderId}`);
  const { data } = await response.json();
  return data;
}
```

### React Example

```jsx
import { useState, useEffect } from 'react';

const API_BASE = 'http://localhost:8000/api/v1';

function ShoppingApp() {
  const [products, setProducts] = useState([]);
  const [cart, setCart] = useState([]);
  const [user, setUser] = useState(null);
  const [order, setOrder] = useState(null);

  // Fetch products on mount
  useEffect(() => {
    fetch(`${API_BASE}/products`)
      .then(res => res.json())
      .then(({ data }) => setProducts(data));
  }, []);

  // Login
  const handleLogin = async (username, password) => {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    const { data } = await res.json();
    setUser(data);
  };

  // Add to cart
  const addToCart = (product) => {
    setCart([...cart, { product_id: product.id, quantity: 1 }]);
  };

  // Checkout
  const handleCheckout = async () => {
    if (!user) {
      alert('Please login first');
      return;
    }

    const res = await fetch(`${API_BASE}/orders`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: user.user_id,
        items: cart
      })
    });
    const { data } = await res.json();
    setOrder(data);
    setCart([]);
  };

  return (
    <div>
      {user ? (
        <div>
          <h2>Welcome, {user.user_id}</h2>
          <div>
            <h3>Products</h3>
            {products.map(p => (
              <div key={p.id}>
                <span>{p.name} - ${p.price}</span>
                <button onClick={() => addToCart(p)}>Add to Cart</button>
              </div>
            ))}
          </div>
          <button onClick={handleCheckout} disabled={cart.length === 0}>
            Checkout
          </button>
          {order && <p>Order placed: {order.order_id}</p>}
        </div>
      ) : (
        <LoginForm onLogin={handleLogin} />
      )}
    </div>
  );
}
```

### Python (Requests)

```python
import requests
import json

API_BASE = 'http://localhost:8000/api/v1'

# List products
products = requests.get(f'{API_BASE}/products').json()['data']
print(products)

# Login
login_res = requests.post(
    f'{API_BASE}/auth/login',
    json={'username': 'testuser', 'password': 'password123'}
)
user_data = login_res.json()['data']
user_id = user_data['user_id']
token = user_data['token']

# Validate token
validate_res = requests.post(
    f'{API_BASE}/auth/validate',
    json={'token': token}
)
print(f"Valid token: {validate_res.ok}")

# Create order
order_res = requests.post(
    f'{API_BASE}/orders',
    json={
        'user_id': user_id,
        'items': [
            {'product_id': products[0]['id'], 'quantity': 2}
        ]
    }
)
order = order_res.json()['data']
print(f"Order created: {order['order_id']}")
print(f"Status: {order['status']}")
print(f"Total: ${order['total_amount']}")

# Get order status
status_res = requests.get(f'{API_BASE}/orders/{order["order_id"]}')
print(status_res.json()['data'])
```

## Error Handling

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad request (invalid input) |
| 401 | Unauthorized (invalid token) |
| 404 | Not found (product/order not found) |
| 500 | Server error |
| 503 | Service unavailable (gateway timeout) |

### Error Response Example

```json
{
  "detail": "Invalid credentials"
}
```

## Best Practices

1. **Always use `/api/v1` gateway** - This provides:
   - Request routing to correct service
   - Error handling and timeouts
   - Health checks
   - Metrics collection

2. **Start with authentication** - All order operations require a user

3. **Cache products locally** - Products rarely change; use Redis cache

4. **Handle payment failures** - Orders may fail at payment step; check `order.payment.status`

5. **Monitor order status** - Poll `/api/v1/orders/{order_id}` to track progress

6. **Add retry logic** - The gateway may timeout; implement exponential backoff in frontend

## Monitoring & Debugging

### Health Check
```bash
curl http://localhost:8000/health
```

### Metrics
```bash
curl http://localhost:8000/metrics
```

### API Documentation (Interactive)
```
http://localhost:8000/docs
http://localhost:8000/redoc
```

## Common Issues

### Issue: CORS Errors

**Solution**: CORS is enabled for all origins. If you still get errors, check browser console and verify the gateway is running.

### Issue: Service Unavailable (503)

**Solution**: One of the backend services is down. Check:
- PostgreSQL is running
- Redis is running
- All services are started

### Issue: Orders fail at payment

**Solution**: This may be intentional simulation. Check payment service logs and try again. The payment service simulates random failures for demo purposes.

## Support

For issues or questions:
1. Check the main README.md for setup instructions
2. Check DEVELOPMENT.md for testing guidance
3. Run tests: `make test` to validate setup
