# Seed de la demo (`seed_demo`)

Fixtures para `python manage.py seed_demo` (ADR 0021). Datos inventados; ninguna persona ni teléfono real.

## Archivos → modelos

| Archivo | Modelo | Clave natural |
|---|---|---|
| `data/brands.json` | `Brand` | `name` |
| `data/customers.json` | `Customer` | `name` |
| `data/materials.json` | `Material` (+ `image`) | `sku` |
| `data/products.json` | `Product` (+ `image`) | `code` |
| `data/product_materials.json` | `ProductMaterial` | (`product`, `material`) |
| `data/suppliers.json` | `Supplier` + `rates[]` → `Rate` | `name` |
| `data/orders.json` | `Order` + `items[]` → `OrderItem` | `code` |
| `data/purchase_orders.json` | `PurchaseOrder` + `items[]`, `progress_reports[]`, `payments[]`, `deliveries[]` | `code` |
| `data/alerts.json` | `Alert` | — |
| `data/decisions.json` | `Decision` (M2M `purchase_orders`) | — |
| `data/style_versions.json` | `StyleVersion` | orden del array = orden de creación |

El estilo base no vive en el seed: la versión `template` sale siempre de `backend/agent/persona/templates/style.base.md`. Las versiones `daily` parten de esa plantilla y cada `style_md` tiene que pasar `validate_style` (sin nombres de proveedores, montos, teléfonos ni frases [G] que nombren al Gerente). Lo propio de cada proveedor va en su `notes` y, en el historial, en el `changelog` como sugerencia.

Orden de carga sugerido: brands, customers, materials, products, product_materials, suppliers, orders, purchase_orders, alerts, decisions, style_versions.

## Referencias
Siempre por clave natural: material por `sku`, producto/orden/pedido por `code`, marca/cliente/proveedor por `name`. Los items de pedido ubican su `Requirement` con (`order`, `kind`, `material`|`product`).

## Fechas
`"T+N"` / `"T-N"` = días respecto del reloj simulado (hoy = `T+0`). Datetimes: `"T-1 14:30"` (hora local del reloj simulado). No hay fechas absolutas.

## Validación
`python validate_seed.py` (en esta carpeta) comprueba referencias, tallas, totales, pagos 50/50, enums, fechas relativas, ausencia de teléfonos y de campos prohibidos, y existencia/tamaño de imágenes.

## Suposiciones
- `stock` es el stock **actual** de almacén, ya descontado lo consumido por órdenes en producción. Algunos requerimientos quedan parcialmente cubiertos (p. ej. drill: 990 m − 350 = 640 m pedidos; antifluido: 440 − 220).
- Cantidades de items de pedidos de insumos (`quantity`, `qty_delivered`) van como decimal string; en talleres/terminado como int.
- `units_done` de pedidos de insumos es 0 salvo que reporten avance (PI-0041 reporta cuellos).
- Pedidos ya entregados o del pasado usan `internal_due_on`/`committed_on` negativos (`T-N`).
- `estimated_on` siempre presente (en entregadas = fecha real de entrega).
- Ítems a medida (ADR 0025 B): `product: null`, `description` con la prenda y `unit_price: null`. La orden queda `broken_down` con `needs_classification` y sin requerimientos hasta que Producción la clasifica. CP-2026-0161 (Colegio Los Algarrobos) es la de la escena de clasificación: un polo deportivo que corresponde a UNI-POD-01 y una casaca cortavientos nueva cuyos insumos (taslan, polar) no existen todavía.
- La planta propia tiene `rates` (costo interno de costura) y pagos en `cash` para que el desglose sea uniforme.
- `Decision.detail` de `approve_assignment` usa precio unitario promedio cuando el pedido tiene varios productos.
- Valores monetarios como string con 2 decimales; `scores`/`rating_score` como número 0–1.
- Escena de la demo: CP-2026-0142 + PT-0038 en `in_progress` con 400/1000 (su `report_token` es fijo: `11111111-1111-4111-8111-000000000038`, así `/report/<token>` se puede ensayar; lo fija el loader, no el JSON); sin pedidos de redistribución, sin `approve_assignment` ni `order_in_danger` de esa orden (pasan en vivo).
- Imágenes: todas generadas (ver `images/credits.md`); 1024 px, < 300 KB.

## Planta (`plant`)

Se carga a `Config.plant_name`, `plant_lat`, `plant_lng`. Inventada, en Piura.

```json
{"plant": {"name": "Planta y Almacén Corpotex, Zona Industrial Piura", "lat": -5.1720, "lng": -80.6580}}
```

Los talleres de Piura y los 4 clientes traen `lat`/`lng` (WGS84). Los proveedores de Lima y México no, van por agencia.
