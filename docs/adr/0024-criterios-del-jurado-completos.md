# 0024. Cubrir los 8 criterios del jurado: vuelven las rutas, pagos a P0, acceso web para talleres y sugerencia de proveedores

- Estado: aceptada (decisión de Oscar). Reemplaza al ADR 0015 (sin rutas) y ajusta el 0021 (seed) y la simplificación del modelo.
- Fecha: 2026-10-10

## Contexto

Los criterios de evaluación del reto (texto oficial) son 8. Al revisar el diseño contra ellos quedaron huecos: las rutas se habían sacado (ADR 0015), los pagos estaban en P1, la simplificación del modelo quitó `rationale` y `scores` del pedido (la justificación del matching), y dos criterios solo estaban cubiertos a medias: el acceso web para que los talleres reporten avance, y la sugerencia de proveedores desde fuentes externas.

| # | Criterio | Estado antes | Qué cambia |
|---|---|---|---|
| 1 | Móvil y computadora; acceso para que los talleres reporten avance con fotos (web o WhatsApp) | WhatsApp sí; web solo el simulador interno | Página pública por pedido para reportar avance (sección C) |
| 2 | Registro de talleres con especialidad, capacidad, precios, calidad y cumplimiento; calificación automática por entrega | Cubierto (`Supplier`, `Rate`, `PurchaseOrder.rating`, `supplier_scores`) | Sin cambio |
| 3 | Matching multicriterio con justificación | La simplificación quitó `rationale` y `scores` | Vuelven, guardados (sección D) |
| 4 | Dividir un pedido grande entre talleres | Cubierto (`redistribute`, `match_requirements`) | Sin cambio |
| 5 | Seguimiento de órdenes a terceros y de pagos (montos depositados y saldos) | Pedidos sí; pagos en P1 | Pagos a P0 (sección D) |
| 6 | Rutas de recojo y entrega con múltiples puntos en Piura (almacén, talleres y clientes), en un mapa | Fuera de alcance (ADR 0015) | Vuelven (sección A) |
| 7 | Sugerir proveedores nuevos desde fuentes externas o autoregistro | Autoregistro en P1; fuentes externas no | Autoregistro a P0; sugerencia externa como tool del asistente, P1 (sección B) |
| 8 | Demo: un taller cancela, redistribuir y recalcular fecha, costo y ruta | Fecha y costo | También la ruta (sección A) |

## A. Rutas (vuelven)

Modelo:

- `Supplier.lat`, `Supplier.lng`; `Customer.lat`, `Customer.lng`; `Config.plant_name`, `Config.plant_lat`, `Config.plant_lng` (el almacén). Todo nullable; sin coordenadas, el punto no entra en la ruta.
- `Route` {date, status: proposed | planned | in_progress | completed | replaced | discarded, distance_km, duration_min, path (GeoJSON LineString), recalculated_from (FK a Route)}.
- `RouteStop` {route, position, kind: pickup | delivery, supplier?, customer?, purchase_order?, order?, name, address, lat, lng, eta}.

Servicio `plan_route(date, *, actor=None) -> Route`:

1. Puntos: el almacén como inicio y fin; un `pickup` por cada pedido de taller con entrega prevista ese día (`committed_on`) en talleres con coordenadas; un `delivery` por cada orden `ready` con cliente con coordenadas.
2. Orden: vecino más cercano desde el almacén más una pasada 2-opt sobre distancias haversine. Sin servicio externo: la ruta se dibuja con líneas rectas. `duration_min` = distancia / 25 km/h + 10 min por parada.
3. Devuelve la `Route` en `planned`; si ya había una `planned` para esa fecha, pasa a `replaced` y la nueva lleva `recalculated_from`.

Redistribución (criterio 8): `redistribute` crea la nueva ruta en `proposed` con `recalculated_from` apuntando a la vigente; el `detail` de la `Decision` `approve_assignment` lleva `before.route_id` y `after.route_id`. Al aprobar, la propuesta pasa a `planned` y la anterior a `replaced`; al rechazar, a `discarded`.

API: `GET /api/routes/?current=1` (la vigente y la reemplazada, con paradas y `path`), `GET /api/routes/<id>/`, `POST /api/routes/plan/ {date}` (Gerente y Producción).

Dashboard: `/routes` con Leaflet y OpenStreetMap (sin API key), centrado en Piura; marcadores de almacén, talleres y clientes; la ruta vigente en línea sólida y la reemplazada punteada; lista de paradas con `eta`. En la escena de la demo, la tarjeta "Redistribución" enlaza a `/routes` con las dos rutas.

Seed: coordenadas reales aproximadas de Piura para el almacén, los 3 talleres y los 4 clientes (Kenji las agrega a su PR; si no llegan, `backend` las pone a mano).

## B. Sugerencia de proveedores (criterio 7)

- Autoregistro pasa a P0: `POST /api/suppliers/self-register/` y la página pública `/supplier-signup`, que crean un `Supplier` con `source = self_registered` y `status = pending_review`. El Gerente los ve en la pestaña "Por revisar" de `/suppliers` y los aprueba o descarta.
- Fuentes externas (P1): tool `suggest_suppliers(specialty, city)` solo para el Gerente en el asistente del dashboard. Es el único turno que habilita la tool `WebSearch` del Agent SDK; busca talleres y proveedores en Piura y Lima y crea `Supplier` con `source = external`, `status = pending_review` y `notes` con la fuente. Nunca activa números ni escribe por WhatsApp. Si no entra a tiempo, el seed trae 2 proveedores `external` en `pending_review` para mostrar la pestaña.

## C. Acceso web para talleres (criterio 1)

- `PurchaseOrder.report_token` (uuid, único). Página pública `/report/<token>` (móvil primero): muestra el pedido (producto, cantidad, fecha), un campo de unidades completadas y subida de foto. `POST /api/report/<token>/` llama a `record_progress(..., source=web)` y crea un `Turn` `message` en la conversación del proveedor si existe, para que el agente acuse recibo por WhatsApp.
- El agente puede mandar el link en el primer mensaje al taller ("si prefieres, reporta aquí: …"). Para la demo es P1; la foto llega igual por WhatsApp y por el simulador.

## D. Lo que la simplificación quitó y vuelve

- `PurchaseOrder.rationale` (texto) y `PurchaseOrder.scores` (json por criterio) vuelven: son la justificación del matching, se generan una sola vez y el dashboard y el asistente las muestran. `candidates` (el ranking completo) sigue en `Decision.detail.proposal`.
- Pagos a P0: `Payment` {purchase_order, kind: advance | balance, amount, status: pending | paid, paid_at, method, receipt}. `mark_payment_paid` (Gerente), `GET /api/payments/`, y en el detalle del pedido `paid_amount` y `pending_amount`. En `/suppliers/<id>` y en el Monitor, el total depositado y el saldo pendiente por proveedor.

## Consecuencias

- Horas extra: rutas ~3 h (backend 1.5, frontend 1.5), pagos ~1 h, autoregistro ~1 h, acceso web ~1 h. Entran en el roadmap; rutas y pagos antes del corte de las 04:30; autoregistro y acceso web si queda tiempo, y si no, en el video.
- El seed necesita coordenadas; se le piden a Kenji sobre su PR.
- `docs/backend/modelo-de-datos.md`, el glosario y el planning se actualizan con esto.
