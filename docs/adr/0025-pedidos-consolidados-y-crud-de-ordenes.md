# 0025. Pedidos de insumos consolidados entre órdenes, generados por Producción; CRUD de órdenes por rol

- Fecha: 2026-10-10 (20:50)
- Estado: aceptada (decisión de Oscar). Ajusta el paso 3 del flujo (CLAUDE.md) y la sección 3 del modelo de datos.

## Contexto

Hoy el flujo crea un pedido por requerimiento al confirmar cada orden: la orden A pide 400 botones y la orden B pide 500 de los mismos botones, y salen dos pedidos al mismo proveedor. En Corpotex el Gerente junta los pedidos de las tres marcas en uno por proveedor (entrevista del 10/10). Oscar pide que los pedidos de insumos se acumulen y que Producción (o el Gerente) los genere cuando lo vea necesario, con sugerencias del sistema; y que exista un CRUD completo de órdenes por rol.

Oscar menciona además "jev" como servicio para clasificar qué productos usar y sugerir crear los materiales que faltan en el inventario (variable `JEV` en `.env`, vacía hasta que él la complete; ver la sección C).

## Decisión

### A. Requerimientos abiertos y pedidos consolidados (insumos)

1. `break_down_order` sigue creando `Requirement` por material (con `qty_from_stock` contra lo disponible, ADR anterior). Al confirmar la orden, los requerimientos de **insumos** NO crean pedidos: quedan en `Requirement.status = open` ("por pedir"). Los de **taller** y **producto terminado** siguen como hoy (un pedido por orden, `suggested` al confirmar), porque son por orden.
2. Vista "Por pedir" (`/purchase-orders/pending`, Producción y Gerente): requerimientos abiertos agrupados por material: SKU, nombre, total por pedir (suma de `qty_to_order` de todas las órdenes abiertas), las órdenes que lo necesitan (código, cantidad, fecha límite más cercana), el proveedor sugerido por el matching (con "Cambiar") y el precio de referencia. Botón **"Generar pedido"** por material y **"Generar todos"**.
3. `generate_purchase_orders(material_ids | all, *, actor)` (`operations/services.py`): por material, toma los requerimientos abiertos, corre `match_requirements` sobre la lista completa (una sola propuesta por material, cantidad = suma), crea UN `PurchaseOrder` `suggested` con un `PurchaseOrderItem` por requerimiento (el FK `requirement` ya existe), cierra los requerimientos (`status = ordered`) y crea la `Decision` `approve_assignment` para el Gerente, como hoy. Un pedido consolidado tiene varias órdenes: `PurchaseOrder.orders` (calculado) y el detalle del pedido las lista; cada orden ve en su detalle el pedido compartido.
4. Fecha límite del pedido consolidado = la más temprana de las órdenes que agrupa; la ruta crítica de cada orden toma la fecha comprometida del pedido compartido.
5. Sugerencia proactiva: el `tick` (B5.2) detecta materiales con requerimientos abiertos cuya fecha límite más cercana esté a menos de `lead_time_days + buffer_days` y abre una `Alert` `purchase_suggested` (una por material) → el asistente de Producción y del Gerente avisa: "Hay 900 botones NX por pedir para CP-2026-0142 y CP-2026-0155; sugiero Avíos Gamarra a S/ 0.18. ¿Genero el pedido?". Con "sí" el asistente llama a `generate_purchase_orders` (tool con confirmación en código, ADR 0017). Producción y Gerente pueden generar; Comercial no.
6. Desglose en bloque (Oscar, 10/10 21:20): `POST /api/orders/break-down/ {order_ids?}` desglosa todas las órdenes `registered` (o las indicadas) de una vez; CTA "Desglosar N registradas" en la lista de Órdenes (Gerente y Producción). Las órdenes se siguen sumando a pedidos ya sugeridos: si `generate_purchase_orders` encuentra un `PurchaseOrder` `suggested` del mismo material y proveedor (aún sin aprobar), agrega los requerimientos nuevos como ítems a ese pedido y recalcula cantidad y fecha límite, en vez de crear otro; la `Decision` pendiente se actualiza.
7. Listas de Órdenes y Pedidos con filtro por estado (`?status=`, varios) y búsqueda por código (`?q=`, por prefijo o parte del código; en pedidos también por código de orden).
8. Seed: la data de Kenji se carga con los pedidos de insumos ya generados (como hoy), más 2-3 requerimientos abiertos de órdenes nuevas (los mismos botones y tela para dos órdenes) para que "Por pedir" tenga contenido y la sugerencia salga en la demo.

### B. CRUD de órdenes por rol

| Acción | Comercial | Gerente | Producción |
|---|---|---|---|
| Crear orden (cliente, marca, ítems, fecha prometida, notas) | sí | sí | no |
| Editar orden (`registered`, `broken_down`) | sí | sí | no |
| Editar orden (`confirmed` en adelante) | no | sí | no |
| Cancelar orden (antes de `in_production`) | sí (propias, hasta `broken_down`) | sí | no |
| Confirmar desglose | no | sí | sí |
| Mover estado de pedidos (avance, entrega, cancelación) | no | sí | sí |
| Generar pedidos consolidados | no | sí | sí |

API: `POST /api/orders/` (ya), `PATCH /api/orders/<id>/` (ítems completos reemplazan; re-desglosa si cambia), `POST /api/orders/<id>/cancel/`, `GET /api/customers/` y `GET /api/products/` para el formulario. Al editar una orden ya desglosada, los requerimientos abiertos se recalculan; los ya pedidos no se tocan (se avisa en la respuesta).

Dashboard: `/orders/new` y `/orders/[id]/edit` con formulario (cliente con búsqueda, marca, ítems con producto y cantidad, fecha prometida, notas); botones según el rol; "Simular orden de Comercial" sigue existiendo como atajo de la demo.

### C. Clasificación con Jev (TypeSafe AI) y materiales faltantes ("creación mágica")

"jev" es **Jev, el modelo System One de TypeSafe AI** (https://docs.typesafe.ai/): se le manda un `state` (texto o JSON) y preguntas tipadas y devuelve respuestas estructuradas con probabilidades calibradas y `confidence`, sin generar texto. Tres primitivas: `Choice` (elige una opción de una lista), `Score` (puntúa en una rúbrica) y `Noul` (sí/no con probabilidad). SDK Python `typesafe-sdk` (`uv add typesafe-sdk`), cliente `TypeSafeClient()` que lee `TYPESAFE_API_KEY`; REST `POST https://api.typesafe.ai/v1/systemone` con `Authorization: Bearer`. Varias preguntas van en una sola llamada (`/patterns/fan-out`).

Jev decide; Claude genera. Al crear o editar una orden, `POST /api/orders/classify/ {items: [{description, quantity}]}`:

1. **Producto** (Jev `Choice`): `state` = descripción del ítem + marca; `criteria` = productos del catálogo (`code: "nombre · marca · materiales"`) más `nuevo`. `confidence >= 0.6` → ese producto; si no, pasa a 2.
2. **Producto nuevo** (Claude `sdk.complete` con esquema JSON): propone código, nombre, marca y lista de materiales (cantidad por prenda, unidad).
3. **Materiales** (Jev, una pregunta por material propuesto): `Choice` contra los SKU del inventario más `nuevo` (`state` = material propuesto + lista de SKU con nombre y unidad). `confidence >= 0.6` → SKU existente; si no, se propone crearlo (SKU, nombre, tipo, unidad) con `Noul` "¿este material es realmente un insumo textil distinto a los existentes?" como guardia.
4. La respuesta trae la propuesta con las confianzas; Producción revisa y confirma en el formulario; `POST /api/orders/apply-classification/` crea producto y materiales nuevos y desglosa la orden.

Sin `TYPESAFE_API_KEY`, los pasos 1 y 3 los hace Claude con el mismo esquema (`confidence` fijo 0.5 y siempre revisión manual). Jev también sirve para puntuar candidatos del matching (`Score` por criterio) si sobra tiempo; no en el alcance de hoy.

## Consecuencias

- Un pedido puede pertenecer a varias órdenes: `PurchaseOrder.order` deja de ser único; se deriva de sus ítems. El Monitor y los detalles muestran "para CP-2026-0142 y CP-2026-0155".
- El flujo de la demo no cambia: la escena de cancelación es de un pedido de taller (por orden). El paso 3 del pitch gana una pantalla: "Por pedir" con la sugerencia del asistente y "Generar pedido".
- Tareas: B6.1 (requerimientos abiertos + `generate_purchase_orders` + endpoints), B6.2 (`purchase_suggested` en el tick), B6.3 (CRUD de órdenes + clientes/productos), B6.4 (clasificación con IA y materiales nuevos, P1), F4.2 ("Por pedir"), F4.3 (formulario de órdenes), A4.1 (tool `generate_purchase_orders` con confirmación y aviso `purchase_suggested`), P3.1 (texto del aviso y de la propuesta).
