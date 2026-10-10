# Contrato de la API

- `openapi.json`: el schema OpenAPI 3 que genera drf-spectacular (`docker compose exec web python manage.py spectacular --file docs/api/openapi.json`). Es la fuente de `frontend/lib/api-types.ts`; se regenera, no se edita.
- `examples/`: payloads de ejemplo que usan el dashboard, el simulador y el seed. Los productos y tallas son los del seed.
- Explorador: `http://localhost:8000/api/docs/` (Swagger), con `Authorization: Token <token>`.

Convenciones (ADR 0009 y 0014): claves en inglés, barra final en todas las URLs, `status` y `kind` con su `*_display` en español, FKs anidadas como `{id, name}` o `{id, code}`, listas sin paginación, URLs de archivos relativas (`/media/...`), fechas ISO en `America/Lima`, montos como strings con dos decimales.

| Endpoint | Rol | Notas |
|---|---|---|
| `POST /api/auth/login/` `{username, password}` → `{token, user}` | público | `user.role` es `manager`, `sales` o `production` |
| `POST /api/auth/logout/` | todos | responde 200 sin revocar el token (dos ventanas del mismo usuario en la demo) |
| `GET /api/auth/me/` | todos | |
| `GET /api/clock/`, `PATCH /api/clock/ {factor?, paused?, advance_hours?}` | GET todos, PATCH Gerente | reloj simulado |
| `GET /api/orders/?status=&risk=&brand=&code=`, `GET /api/orders/<id>/` | todos, por rol | `code` exacto |
| `GET /api/purchase-orders/?status=&kind=&order=&supplier=&waiting_manager=1&code=`, `GET /api/purchase-orders/<id>/` | todos, por rol | sin precios ni términos para `sales` y `production` |
| `GET /api/suppliers/?kind=&status=&source=`, `GET /api/suppliers/<id>/` | Gerente | con números, tarifas y `payments_summary` por moneda |
| `GET /api/payments/?status=pending\|paid` | Gerente | `due_on` y `status` calculados |
| `GET /api/monitor/` | todos, por rol | `{clock, kpis, alerts, decisions, redistributions, orders_in_danger, payments_by_supplier}` |
| `GET /api/schema/`, `GET /api/docs/` | todos | |

Lo que sigue (B3 y B4): `POST /api/orders/` (`examples/order-*.json`), `/api/manager/*`, `/api/alerts/<id>/acknowledge/`, `/api/simulator/*`, `/api/conversations/<id>/messages/`, `/api/assistant/*`, `/api/me/badges/`, `/api/routes/*`, `/api/onboarding/*`, `/api/settings/claude/*`, `/api/style/*`, `/webhooks/evolution/<secret>/`.
