# 0029. Ficha técnica editable por prompt, fechas de la ruta crítica visibles, foto del ítem guardada

- Fecha: 2026-10-11 (05:50)
- Estado: aceptada (pedido de Oscar, 11/10 05:45). Ajusta el ADR 0028.

## Contexto

Oscar pide tres cosas sobre la orden: que la foto que sube Comercial se guarde y se vea en el detalle; que en el detalle se vean las fechas estimadas de cada paso y que "prometida" pase a llamarse "fecha de entrega"; y que Producción y el Gerente puedan cambiar el desglose por prompt (insumos, cantidades, pasos) y que "desglose" y "Confirmar desglose" cambien de nombre.

## Decisión

### 1. Nombres

- El desglose de una orden pasa a llamarse **ficha técnica**: es el término que usa el sistema de producción de Corpotex (entrevista del 10/10). "Insumos por prenda" es la **receta** del producto. El botón "Confirmar desglose" pasa a **"Aprobar y abastecer"** (Oscar, 11/10 04:30: dice lo que pasa, la ficha se aprueba y los insumos entran a "por pedir"); el estado `broken_down` se muestra como "Con ficha técnica". La sección del detalle que compara insumos y talleres con el stock se titula **"Ficha técnica"** con el subtítulo "Insumos y tercerización con talleres".
- "Prometida al cliente" pasa a **"Fecha de entrega"** en el formulario, el detalle, las listas, los avisos del asistente y los textos del agente. El campo de la API sigue siendo `promised_on`.

### 2. Foto del ítem

`OrderItem.photo` (ImageField, `items/`). `POST /api/orders/` y `PATCH` aceptan en cada ítem `photo: {media_type, data}` (base64, la misma imagen reducida que ya se manda a `describe-image`); el detalle expone `items[].photo_url`. El formulario manda la foto con el ítem; el detalle la muestra como miniatura ampliable junto a la descripción.

### 3. Fechas de la ruta crítica

El detalle muestra cada paso de `critical_path` con sus fechas: una línea de tiempo con eje de fechas (hoy, estimada, entrega), y debajo la lista de pasos con "del 12 al 14 oct", el paso crítico marcado y, en los pasos de insumos y taller, la fecha comprometida por el proveedor contra la fecha límite interna. Arriba, tres datos: Fecha de entrega, Estimada y Holgura (días), con color por riesgo.

### 4. Ficha técnica editable por prompt (Producción y Gerente)

- **Modelo.** `OrderItem.bom_override` (JSON, lista de `{material_id | new: {sku, name, kind, unit}, qty_per_unit}`): cuando existe, `break_down_order` la usa en vez de la receta del producto, solo para esta orden; la receta del catálogo no cambia. `Order.stage_overrides` (JSON `{stage: days}`): `compute_critical_path` lo usa en vez de `Config.stage_durations` para esta orden.
- **Servicio** `revise_order(order, instruction, *, actor, dry_run)`: manda a Claude la ficha actual (ítems con producto, receta efectiva por prenda y cantidades), los SKU del inventario, los pasos con sus días y la instrucción en lenguaje natural ("agrega 2 botones por polo", "cambia la tela a drill", "quita la etiqueta de la casaca", "el corte toma 3 días"). Devuelve un cambio estructurado `{items: [{item_id, materials: [...]}], stage_overrides: {...}, summary}` con un resumen en español de lo que cambia. Con `dry_run` no guarda nada; sin él, aplica los overrides, vuelve a desglosar (`rebreak_down_order`, sin tocar requerimientos ya pedidos) y recalcula la ruta crítica. Jev confirma los SKU existentes como en el clasificador; `CLASSIFY_MODEL` para la generación.
- **API.** `POST /api/orders/<id>/revise/ {instruction, dry_run?}` (Gerente y Producción). Responde la propuesta con `summary` y, sin `dry_run`, la orden actualizada.
- **Dashboard.** En el detalle, bajo la ficha técnica, un campo "Ajustar la ficha técnica con una instrucción" con botón "Proponer": muestra la propuesta como diff (insumos que entran, salen o cambian de cantidad; pasos que cambian de días) y "Aplicar". Se puede hacer antes o después de aprobar; después de aprobar, los requerimientos ya pedidos no se tocan y la respuesta lo avisa.
- **Asistente.** Tool `revise_order(order_code, instruction)` para Gerente y Producción, con confirmación en código: vista previa con el `summary`, "sí" aplica.

## Consecuencias

- Una orden puede tener una ficha distinta de la receta del catálogo; el catálogo sigue siendo la referencia para órdenes nuevas. Si Corpotex quiere que un cambio pase al catálogo, se edita el producto.
- Tareas: N1 backend (foto), N2 backend (overrides, `revise_order`, endpoint), N3 disenador (fechas y nombres), N4 disenador (foto en el detalle y campo de ajuste), N5 agente (tool `revise_order`), N6 personalidad (textos "fecha de entrega" y "ficha técnica").
