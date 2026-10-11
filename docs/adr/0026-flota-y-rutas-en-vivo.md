# 0026. Flota de vehículos, planificación de entregas por vehículo y seguimiento en vivo

- Fecha: 2026-10-10 (23:20)
- Estado: aceptada (pedido de Oscar, 10/10 23:15). Amplía la sección de rutas del ADR 0024. Lo implementa la sesión `rutas`.

## Contexto

Hoy `/routes` planifica una sola ruta por día con todas las órdenes abiertas de esa fecha. Oscar pide:

- Ver las órdenes **listas** (`ready`) y **entregadas** (`delivered`), filtrando por fechas.
- Varios vehículos. A cada uno, Producción le asigna las órdenes que va a entregar. Esta planificación se hace cada vez que hay órdenes por entregar, y se pueden programar órdenes listas para otras fechas.
- Seguir un vehículo hoy: su posición en "tiempo real" por una API que también la guarda, con una muestra cada 5 minutos. El dashboard la consume por SSE y muestra en movimiento los vehículos que se elijan con checkboxes.
- Un mapa más inteligente y atractivo, que se pueda ver a pantalla completa.

## Decisión

### 1. Modelo (app nueva `fleet` y cambios en `operations`)

| Modelo | Campos | Notas |
|---|---|---|
| `fleet.Vehicle` | `name`, `plate`, `kind` (`van`, `pickup`, `motorcycle`, `truck`), `capacity_units` (prendas), `color` (hex), `driver_name`, `is_active`, `last_lat`, `last_lng`, `last_heading`, `last_speed_kmh`, `last_seen_at` | Se gestiona desde el admin de Django. La API es de lectura para los roles con acceso a rutas. |
| `fleet.VehiclePosition` | `vehicle`, `route` (null), `lat`, `lng`, `heading`, `speed_kmh`, `recorded_at`, `source` (`simulator`, `device`, `manual`) | Historial muestreado, con índice `(vehicle, recorded_at)`. |
| `Route` | `+ vehicle` (FK null), `+ started_at`, `+ completed_at` | Hay una ruta vigente (`planned` o `in_progress`) por vehículo y día. Una ruta sin vehículo es la "proyectada" de la redistribución (ADR 0024) y no cambia. |
| `RouteStop` | `+ delivered_at` | La parada entregada pasa la orden a `delivered` si estaba `ready`. |
| `Order` | `+ scheduled_delivery_on` (date null), `+ delivery_address`, `+ delivery_lat`, `+ delivery_lng` (null: se usa el cliente) | `delivery_date(order)` = `scheduled_delivery_on`, si no `estimated_on`, si no `promised_on`. La dirección propia de la orden sirve, por ejemplo, para las agencias de Caja Piura. |

### 2. Planificación inteligente por vehículo (`operations/routes.py`)

`plan_day(date, *, vehicle_ids=None, order_ids=None, actor)` (Producción y Gerente):

1. **Bolsa del día.** Las órdenes `ready` con `delivery_date == date` que no estén en una ruta `in_progress`. También las atrasadas: `ready` con fecha anterior y sin entregar. Se ordenan por prioridad: atrasadas primero, luego por `promised_on`.
2. **Reparto por barrido.** Se ordenan los puntos por el ángulo desde la planta y se llenan los vehículos activos en turno. Cada vehículo tiene dos límites: `capacity_units` (la suma de prendas de sus órdenes) y la jornada, de 08:00 a 18:00 (`SHIFT_END_HOUR`).
3. **Orden de paradas por vehículo.** Vecino más cercano más 2-opt, con `order_stops`, que ya existe.
4. **Mejora.** Se intenta pasar cada parada al vehículo vecino. El cambio se queda si baja la distancia total y no rompe ningún límite.
5. **Lo que no entra.** Va a `unassigned`, con un motivo ("capacidad", "jornada", "sin coordenadas") y la sugerencia de pasarlo al día siguiente. Con un clic se aplica `scheduled_delivery_on = date + 1`.
6. **Justificación por ruta.** Por ejemplo: "4 entregas · 1 450 prendas (73 % de capacidad) · 18 km · vuelve 12:40". Por parada: la ETA y si llega a tiempo frente a `promised_on`.

Una nueva planificación de ese día reemplaza las rutas `planned` de los vehículos implicados; las anteriores pasan a `replaced`. Las rutas `in_progress` no se tocan. `plan_route` y `propose_for_redistribution` siguen como están para la escena del jurado.

### 3. API (`/api/`)

Despacho (`dispatch`) es la entrega de una orden al cliente. Se distingue de `Delivery`, que es la entrega de un proveedor en planta.


| Método y ruta | Rol | Qué hace |
|---|---|---|
| `GET dispatches/?status=ready,delivered&from=&to=&vehicle_ids=&unassigned=1` | Gerente, Producción; Comercial solo lee | Órdenes listas o entregadas con su entrega: `{order: {id, code, customer_name, units, promised_on}, status, scheduled_on, delivered_at, address, lat, lng, route_id, vehicle: {id, name, color} \| null, stop: {position, eta} \| null, on_time}` |
| `PATCH dispatches/<order_id>/ {scheduled_on?, vehicle_id?}` | Gerente, Producción | Reprograma la orden a otra fecha o la mueve a otro vehículo. Reoptimiza las rutas `planned` afectadas. |
| `GET vehicles/` | los tres | Vehículos con su última posición |
| `POST routes/plan-day/ {date, vehicle_ids?, order_ids?}` | Gerente, Producción | `{routes: [RouteDetail], unassigned: [{order_id, code, reason}], suggested_next_day: [order_id]}` |
| `POST routes/<id>/start/` · `POST routes/<id>/complete/` | Gerente, Producción | Pasa la ruta a `in_progress` o a `completed`. |
| `POST routes/<id>/stops/<stop_id>/deliver/` | Gerente, Producción | Marca la parada entregada y la orden pasa a `delivered`. |
| `POST vehicles/<id>/positions/ {lat, lng, heading?, speed_kmh?, recorded_at?, source?}` | Gerente, Producción (y el simulador) | Actualiza `Vehicle.last_*` siempre. Guarda un `VehiclePosition` solo si pasaron `VEHICLE_SAMPLE_SECONDS` desde la última muestra (300 por defecto, configurable en `.env`). Responde `202 {stored}`. |
| `GET vehicles/<id>/positions/?from=&to=` | los tres | Historial guardado, para dibujar la estela. |
| `GET vehicles/live/?ids=1,2` | los tres | Foto actual, para el respaldo por polling. |
| `GET vehicles/stream/?ids=1,2` | los tres | SSE (sección 4) |
| `POST vehicles/<id>/simulate/ {speed_factor=12, interval_s=3}` · `DELETE` | Gerente, Producción | Arranca o detiene la simulación (sección 5). |

### 4. SSE

- Usa `StreamingHttpResponse` con `Content-Type: text/event-stream`, `Cache-Control: no-cache, no-transform` y `X-Accel-Buffering: no`.
- Eventos:
  - Al conectar llega un `snapshot` con la foto de los vehículos pedidos.
  - Llega un `position` con `{vehicle_id, lat, lng, heading, speed_kmh, at, route_id, next_stop: {position, name, eta}}` cada vez que cambia `last_seen_at`.
  - Llega un `stop` con `{route_id, stop_id, order_code, delivered_at}` al entregar una parada.
  - Llega un comentario `: ping` cada 15 s.
- El generador lee `Vehicle.last_*` cada segundo y llama a `close_old_connections()` en cada vuelta. Cierra a los 10 minutos y el cliente se reconecta con `Last-Event-ID`. `runserver` corre con hilos: cada conexión ocupa uno, lo que basta para la demo.
- Autenticación: el front usa `Token` en el header, y `EventSource` no manda headers. Por eso el cliente lee el stream con `fetch` y un `ReadableStream`, y separa los eventos SSE a mano.
- Respaldo: si el stream no llega por la reescritura de Next o por el tunnel, el front pasa a polling de `vehicles/live/` cada 3 s. Hay que verificarlo en `:3000` y en `https://corpotex.oscargicast.com`.

### 5. Simulador

El simulador es una tarea Celery que **se reprograma sola**. Cada tick avanza el vehículo y vuelve a encolarse con `countdown=interval_s`. Nunca es una tarea larga: el worker tiene 3 hilos que comparte con los turnos de WhatsApp.

- Cada tick recorre el `path` de la ruta `in_progress` del vehículo. Avanza `speed_kmh × speed_factor × interval_s` sobre los tramos rectos y publica por la misma función que usa `POST positions`, con `source=simulator`.
- Al llegar a una parada espera `STOP_MINUTES / speed_factor` y la marca entregada. Al volver a la planta completa la ruta y se detiene.
- El estado vive en `Vehicle`: `sim_active`, `sim_progress_m` y `sim_speed_factor`. Va en la cola `periodic`.
- Solo entrega órdenes de rutas que Producción inició. Nunca toca las órdenes del guion del jurado.

### 6. Dashboard `/routes` (rediseño)

```
+--------------------------------------------------------------------------+
| Rutas   [Planificar] [En vivo] [Entregadas]      < sáb 11 oct >    [ ⤢ ] |
+----------------------+---------------------------------------------------+
| Vehículos            |                                                   |
| [x] Furgón 1  ● 3/7  |        MAPA (teselas CARTO claras)                |
|     vuelve 12:40     |        - una ruta por vehículo, en su color       |
| [x] Camioneta ● 1/4  |        - vehículo animado con rumbo y pulso       |
| [ ] Moto      ○      |        - paradas numeradas; entregadas con check  |
|----------------------|        - estela de muestras cada 5 min            |
| Sin asignar (3)      |                                                   |
|  CP-2026-0163  Mover |                       [Ajustar] [Seguir Furgón 1] |
|  "no cabe: capacidad"|                                                   |
| [Planificar el día]  |                                                   |
+----------------------+---------------------------------------------------+
```

- **Pestañas.**
  - **Planificar** (Producción y Gerente): elegir fecha, ver la bolsa de órdenes listas, "Planificar el día" y una columna por vehículo con su barra de capacidad. Cada orden tiene "Mover" (a otro vehículo) y "Reprogramar" (a otra fecha), y "Sin asignar" muestra el motivo.
  - **En vivo** (los tres roles): checkboxes por vehículo, que controlan tanto las capas del mapa como la suscripción SSE. Cada vehículo muestra su línea de tiempo de paradas (ETA contra hora real), su progreso "3/7 entregas", "Iniciar ruta" y "Simular".
  - **Entregadas**: rango de fechas con atajos (Hoy, Ayer, Últimos 7 días) y lista con hora de entrega, vehículo y a tiempo o tarde.
- **Mapa.**
  - Pantalla completa con la Fullscreen API sobre el contenedor del mapa, más `map.invalidateSize()`. Esc sale de pantalla completa. Con pantalla completa, el panel lateral pasa a un cajón flotante plegable.
  - Botones "Ajustar a vehículos" y "Seguir" por vehículo.
  - Teselas CARTO Positron, con atribución, para que las rutas de colores resalten. OSM queda de respaldo.
- **Movimiento.** El marcador se interpola entre dos posiciones durante el intervalo, con `requestAnimationFrame` y transform, y gira según el rumbo. Con `prefers-reduced-motion`, salta sin animar. Un punto que late indica señal en vivo (menos de 30 s); a los 2 min sale "sin señal" en gris.
- **Color y accesibilidad.**
  - La paleta de vehículos es Okabe-Ito (`#0072B2`, `#E69F00`, `#009E73`, `#CC79A7`, `#D55E00`, `#56B4E9`), apta para daltonismo.
  - El color nunca va solo: siempre lleva el nombre del vehículo y el estado con icono y texto ("Entregada", "Atrasada").
  - Iconos Lucide (`Truck`, `Factory`, `MapPin`, `Maximize2`), sin emoji.
  - Las ETA usan números tabulares.
  - Se mantienen la tipografía y los tokens actuales del dashboard.
- **Móvil.** El mapa ocupa `60dvh` y debajo hay una hoja con las pestañas. En pantalla completa, un chip flotante "Vehículos" abre los checkboxes. Los objetivos táctiles miden 44 px o más.
- **Estado en la URL.** `?tab=live&date=2026-10-11&v=1,2&from=&to=`, para compartir o volver.

### 7. Seed

- 3 vehículos: Furgón 1 (1 500 prendas), Camioneta 2 (800) y Moto 3 (150).
- Unas 10 órdenes `ready` para hoy y mañana en unos 8 puntos de Piura: agencias de Caja Piura como dirección de la orden, y 3 o 4 colegios nuevos como clientes, con coordenadas reales de Piura y Castilla.
- 3 órdenes `delivered` de ayer con su ruta `completed` y su estela.
- Las alertas abiertas del guion no cambian: `payment_due` de CP-2026-0118, `order_in_danger` de CP-2026-0158 y CP-2026-0151, y `purchase_suggested` de RIB-CUE-01 y HIL-POL-40.
- No se tocan las órdenes del guion. CP-2026-0118 sigue con su fecha.

## Consecuencias

- La escena del jurado sigue igual: la redistribución arma rutas sin vehículo ("proyectadas") y `redistribution-card.tsx` y `route-map.tsx` las siguen mostrando. Si la orden afectada ya estaba en una ruta con vehículo, la propuesta conserva ese vehículo.
- Antes de cada merge: `pytest` en verde, incluidos el D1 y los tests de redistribución, más `pnpm typecheck` y `pnpm build`. La `rutas` es dueña de `backend/fleet/**`, `backend/operations/routes.py`, las vistas y serializers de rutas y entregas, y `frontend/app/(dashboard)/routes/**`. Backend y disenador no tocan esos archivos mientras dure.
- Tareas y tiempos en `docs/planning.md` (R1 a R4). El congelamiento de alcance es a las 04:30: lo que no esté en verde a esa hora no entra, y `/routes` sigue como hoy.
