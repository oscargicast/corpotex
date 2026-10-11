# 0028. Orden "mágica": la clasificación ocurre mientras Comercial escribe, y la orden nace desglosada

- Fecha: 2026-10-11 (02:10)
- Estado: aceptada (pedido de Oscar, 11/10 02:05). Ajusta el ADR 0025 B y C.

## Contexto

Hoy Comercial crea la orden con ítems en texto libre, la orden queda "pendiente de clasificar" y Producción tiene que abrir el detalle y pulsar "Desglosar componentes" para que Jev y Claude propongan producto e insumos. Oscar pregunta por qué hace falta esa acción, y pide que el formulario `/orders/new` sea mágico: que la clasificación se vea en tiempo real mientras se escribe, y que al guardar la orden ya esté desglosada. Es el elemento "wow" del pitch. También pide quitar el botón "Simular orden de Comercial" de la lista de órdenes, porque el formulario real lo reemplaza.

Oscar plantea además si al crear la orden los pedidos deberían ir naciendo solos y acumularse en una compra más grande. Eso ya existe: `break_down_order` crea un `Requirement` por material y orden, y "Por pedir" (hoy el filtro de Inventario) los suma por material; cada `PurchaseOrderItem` apunta a su `Requirement`, así que un pedido consolidado sabe qué cantidad es de cada orden, y la separación por proveedor sigue siendo una decisión del Gerente al aprobar (ADR 0025 A). Lo que falta es que ese desglose no espere una acción.

## Decisión

### 1. Clasificación en vivo, sin orden guardada

`POST /api/orders/classify-draft/` (Comercial, Producción y Gerente) recibe `{brand, items: [{key, description, quantity}]}` y devuelve la misma propuesta que `classify` por ítem, con `key` en vez de `item_id`. Internamente reutiliza `classify_item` con un `OrderItem` no guardado. Clasifica solo los ítems cuya `description` tiene 12 caracteres o más y una cantidad; los demás vuelven con `status: "pending"`. Sin `TYPESAFE_API_KEY`, igual que hoy: Claude sola.

Para que el formulario no espere a todos, el endpoint acepta un solo ítem a la vez; el front lo llama por ítem, en paralelo. Tiempo esperado: unos 3 s por ítem con Jev cuando es un producto del catálogo (una llamada de Jev, sin Claude) y unos 10 s cuando es un producto nuevo (Jev más Claude).

### 2. Guardar ya desglosado

`POST /api/orders/` acepta, opcional, `classification: {items: [{key, product: {existing_id | new}, materials: [...]}]}`, con el mismo shape que `apply-classification` pero por `key`. Si viene, `register_order` crea producto e insumos nuevos, asigna el producto a cada ítem y desglosa (`break_down_order`) en la misma transacción. La orden nace `broken_down`, con `needs_classification = false`, y entra a "Por pedir" sin que Producción toque nada. Sin `classification`, se comporta como hoy.

`PATCH /api/orders/<id>/` acepta lo mismo para los ítems nuevos de una edición.

### 3. El formulario (`/orders/new`)

- **Un ítem es una línea de texto**, como escribe el cliente: "300 polos deportivos azul marino con escudo sublimado, tallas 6 a 14". El front separa la cantidad si va al inicio; si no, pide la cantidad aparte.
- **Al dejar de escribir** (600 ms sin teclear, o al salir del campo) la línea muestra un estado animado "Reconociendo…" y llama a `classify-draft`. La respuesta se pinta en la misma tarjeta, debajo del texto:
  - **Producto reconocido:** chip verde "Polo deportivo UNICRACK · 88 %" y la lista de insumos con cantidad por prenda.
  - **Producto nuevo:** chip ámbar "Producto nuevo · Casaca cortavientos" y los insumos, marcando con "Nuevo" los que no están en inventario.
  - Cada insumo se puede quitar y cada cantidad se puede corregir en línea; "Cambiar producto" abre el buscador del catálogo.
- **Resumen vivo** a la derecha (abajo en móvil): total de prendas, insumos a comprar sumados entre ítems ("400 cuellos rib · 1 200 botones"), cuántos insumos son nuevos, y la fecha prometida contra la ruta crítica estimada ("necesita 12 días; prometida en 10 → en riesgo", calculada con `lead_time_days` de los proveedores sugeridos más `buffer_days`).
- **Guardar** envía la orden con `classification`. La confirmación dice "Orden CP-2026-0184 creada y desglosada: 5 insumos por pedir" y lleva al detalle. Si algún ítem sigue sin clasificar porque falló la IA, se guarda como hoy y la orden queda "por clasificar" solo para ese ítem.
- **Movimiento:** la tarjeta del ítem crece con el resultado (altura animada con `grid-template-rows`, 250 ms), los insumos entran escalonados 30 ms, y `prefers-reduced-motion` desactiva todo. El indicador de "Reconociendo…" es un shimmer, no un spinner.
- **Accesibilidad:** los chips llevan texto, no solo color; `aria-live="polite"` en el resumen; los botones de quitar insumo miden 44 px en móvil.

### 3b. Foto de la prenda en vez de texto (Oscar, 11/10 03:45)

Cada ítem acepta una foto (adjuntar, arrastrar o pegar) además del texto. `POST /api/orders/describe-image/` (los tres roles) recibe `{image: {media_type, data (base64)}, brand?, customer?}` y devuelve `{description}`: Claude describe la prenda en una frase de hasta 25 palabras en español (tipo de prenda, color, cuello, mangas, cierres, detalles), sin cantidad. Medido con el modelo real: 4 a 5 s. La frase cae en el campo de texto del ítem, editable, y dispara el reconocimiento de siempre; la cantidad es obligatoria y la escribe Comercial. Jev no ve imágenes: la foto siempre pasa por Claude primero. El front reduce la foto a 1 568 px de lado largo y JPEG antes de subirla (límite 5 MB). La foto no se guarda con la orden en esta versión.

### 4. Lo que se va

- El botón "Simular orden de Comercial" de `/orders`. El componente queda en el repo solo si el guion lo necesita como atajo (`docs/demo/guion-visual.md` paso 3 pasa a usar `/orders/new`).
- "Desglosar componentes" en el detalle de la orden se mantiene para órdenes viejas o con ítems que la IA no pudo clasificar; para una orden nacida desglosada no aparece.

### 5. Demo

Paso 3 del guion: Comercial abre `/orders/new`, elige Caja Piura, escribe dos líneas y, mientras habla, los dos ítems se reconocen solos; guarda y la orden aparece desglosada. Unos 25 s. CP-2026-0161 sigue en el seed como respaldo para "Desglosar componentes".

## Consecuencias

- `classify-draft` llama a Jev y a Claude sin guardar nada: una orden de 5 ítems son hasta 5 llamadas a Claude en paralelo. Para la demo es aceptable; en producción conviene un límite por usuario.
- Tareas: M1 backend, M2 disenador, M3 backend (clasificación automática en segundo plano para órdenes por API), M4 backend (`describe-image`) y M5 disenador (foto en el ítem), en `docs/planning.md`. No hay hora de cierre (Oscar, 11/10 04:20): se mergea lo que esté en verde hasta el pitch; si la foto no está, el formulario de texto sigue igual.
