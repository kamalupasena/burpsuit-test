# Serendib Pay Burp Suite API Lab

An intentionally vulnerable API for authorized classroom practice with Burp Suite. It runs as a local Docker container, uses fictional seeded data, and does not make outbound requests or run submitted input as code.

## Run locally

Requires Docker with Compose support.

```sh
docker compose up --build
```

The API is available at `http://127.0.0.1:8081`; the container listens on 8080 internally, while the host port is explicitly bound to loopback. In Burp, leave the proxy listener on its common port `127.0.0.1:8080` and configure the browser to use Burp as its proxy. Browse to `http://127.0.0.1:8081` through that browser.

Check `GET /health` and `GET /api/docs`. Stop with `Ctrl+C`. No persistent volume is used; data resets when the container is recreated.

## Seeded accounts

| Username | Password | Role |
|---|---|---|
| `alice` | `alice123` | user |
| `bob` | `bob123` | user |
| `admin` | `admin123` | admin |

These credentials are public lab fixtures and must never be reused outside this lab.

## Suggested Burp exercises

1. **Proxy and discovery:** visit `/api/docs`, send a request to Repeater, and note methods, status codes and JSON shapes.
2. **Authentication and sessions:** log in with `POST /api/auth/login` using JSON, inspect the response cookie and token, compare `/api/me` before and after login, then test logout.
3. **SQL injection:** inspect the login request and validate the deliberately unsafe query only against this service and its fictional database.
4. **Object access:** authenticate as Alice, compare `GET /api/orders` with `GET /api/orders?user_id=2`; inspect and safely modify `GET/PATCH /api/users/2`.
5. **Role authorization:** log in as Alice and request `/api/admin/reports`; compare with the admin account.
6. **Mass assignment and validation:** submit an order with a changed `user_id`, then try missing, malformed, and boundary values for `product_id` and `quantity`.
7. **Search and errors:** vary `q` on `/api/search` and record the API's input handling and response behavior.

All cases are deliberately vulnerable: login SQL construction, cross-account profile/order access, an authenticated-user-only admin check, and client-controlled order ownership. The search endpoint is parameterized and intended as a comparison/control. The service is a teaching replica, not an application to deploy.

## Reset

`POST /api/lab/reset` clears in-memory sessions and restores the seeded data. Recreating the container also resets everything.

## Boundaries

Use only on a machine or isolated classroom network where you are authorized to run the lab. Keep it bound to loopback; do not expose it to the internet or a shared network. It contains intentional weaknesses and simple demo credentials.
