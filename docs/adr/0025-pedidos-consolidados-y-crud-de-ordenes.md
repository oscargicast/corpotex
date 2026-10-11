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
6. Seed: la data de Kenji se carga con los pedidos de insumos ya generados (como hoy), más 2-3 requerimientos abiertos de órdenes nuevas (los mismos botones y tela para dos órdenes) para que "Por pedir" tenga contenido y la sugerencia salga en la demo.

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

### C. Clasificación con IA al crear la orden y materiales faltantes ("creación mágica")

Al crear o editar una orden, si un ítem no corresponde a un producto del catálogo o el producto no tiene lista de materiales, el sistema propone (modelo con `sdk.complete` y esquema JSON): el producto del catálogo más cercano o uno nuevo (código, nombre, marca) y su lista de materiales (SKU existente o material nuevo: SKU, nombre, tipo, unidad, cantidad por prenda). Producción revisa y confirma; con eso se crean producto/materiales y se desglosa. Es el lugar donde entra "jev" si es un servicio externo de clasificación: `JEV` en `.env` (vacío → se usa el modelo de Claude; con valor → se consulta jev primero). Pendiente: Oscar define qué es jev y su API.

## Consecuencias

- Un pedido puede pertenecer a varias órdenes: `PurchaseOrder.order` deja de ser único; se deriva de sus ítems. El Monitor y los detalles muestran "para CP-2026-0142 y CP-2026-0155".
- El flujo de la demo no cambia: la escena de cancelación es de un pedido de taller (por orden). El paso 3 del pitch gana una pantalla: "Por pedir" con la sugerencia del asistente y "Generar pedido".
- Tareas: B6.1 (requerimientos abiertos + `generate_purchase_orders` + endpoints), B6.2 (`purchase_suggested` en el tick), B6.3 (CRUD de órdenes + clientes/productos), B6.4 (clasificación con IA y materiales nuevos, P1), F4.2 ("Por pedir"), F4.3 (formulario de órdenes), A4.1 (tool `generate_purchase_orders` con confirmación y aviso `purchase_suggested`), P3.1 (texto del aviso y de la propuesta).
