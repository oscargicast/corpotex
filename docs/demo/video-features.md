# Video de features: qué grabamos y en qué orden

Mapa de las mejores features del producto para el video de Remotion (`video/`, ADR 0032). Es un video aparte del respaldo de la demo (`docs/demo/respaldo/`): no sigue el guion del pitch minuto a minuto, sino que muestra cada feature por separado, en el orden en que la vive Corpotex. Fuente: ideas de Oscar, 11/10.

Cómo se usa:

1. Las grabaciones de pantalla las hace sola `video/record.mjs` (Playwright headless contra el stack, una toma por escena, en `video/public/recordings/`). Corre con `node record.mjs` desde `video/`, o `SCENES=02,03 node record.mjs` para repetir algunas. Muta datos (orden nueva, aprobaciones, la cancelación de PT-0038 por el contacto simulado, la simulación del Furgón 1): después hay que correr `seed_demo --reset-chats`. Nunca escribe al número real de Valeria.
2. Mientras un archivo no existe, el video muestra un marcador con el nombre que falta. Las frases de cada escena son subtítulos que cambian solos; se editan en `video/src/CorpotexFeatures.tsx` o en Remotion Studio.
3. Duración: 4 min 49 s con las grabaciones del 11/10 (cada escena dura lo que su grabación a la velocidad indicada; se recorta con `recordingStartAt` o se acelera con `recordingPlaybackRate`).

La escena 1 muestra el QR con una respuesta simulada del API (`page.route`): la instancia real nunca se desconecta. Las escenas 6 y 7 usan contactos simulados; en horas de silencio (`QUIET_HOURS`) el agente igual responde al instante a un mensaje entrante del simulador, y en la grabación del 11/10 también mandó los primeros contactos a los proveedores simulados de los pedidos recién aprobados.

## Orden de las escenas

| # | Escena | Rol | Dura | Archivo |
|---|---|---|---|---|
| 0 | Intro | — | 4 s | (generada) |
| 1 | Puesta en marcha: Claude, WhatsApp por QR y estilo del Gerente | Gerente | 24 s | `01-onboarding.mp4` |
| 2 | Orden mágica: por texto o foto, con insumos sugeridos | Comercial | 36 s | `02-orden-magica.mp4` |
| 3 | Producción revisa, ajusta por prompt y aprueba | Producción | 29 s | `03-produccion-ajusta.mp4` |
| 4 | Pedido en lote: reserva, "por pedir" y el agente escribe a los proveedores | Producción → Gerente | 31 s | `04-pedido-en-lote.mp4` |
| 5 | Proveedores medidos y matching por histórico | Gerente | 27 s | `05-matching.mp4` |
| 6 | WhatsApp en vivo: el dashboard se actualiza solo con cada respuesta | Gerente | 46 s | `06-whatsapp-en-vivo.mp4` |
| 7 | Cancelación: avisos a todos, sin precios | Gerente y Comercial | 50 s | `07-avisos-por-rol.mp4` |
| 8 | Rutas y flota en vivo | Producción | 43 s | `08-rutas.mp4` |
| 9 | Cierre | — | 5 s | (generada) |

## Escenas

### 1. Puesta en marcha (Gerente)

Idea de Oscar: "un flow en donde se muestre un QR de WhatsApp, se integre con Claude como paso inicial del Gerente".

- Pantalla: `/settings` con "Puesta en marcha" en 0/3. Entrar a `/settings/claude` y conectar la cuenta (ADR 0022). Volver, entrar a `/settings/whatsapp`: aparece el QR de la instancia `corpotex` (no hace falta escanearlo en la grabación; basta verlo y luego cortar al estado "Conectado"). Terminar en `/settings/style` con el borrador del estilo del Gerente sacado de sus chats y el botón "Aprobar".
- Frases: "El Gerente conecta su cuenta de Claude una sola vez." / "Vincula el WhatsApp de la empresa escaneando un QR." / "El sistema aprende cómo escribe el Gerente a partir de sus chats."
- Cuidado: el QR se graba en un ambiente limpio (una instancia de prueba o el estado del seed), nunca el de producción con el número de Oscar. Si no hay tiempo de montar una instancia limpia, se graba `/settings/whatsapp` ya conectada y el QR se muestra desde la pantalla de Evolution de una instancia nueva.

### 2. Orden mágica (Comercial)

Idea: "creación de órdenes por prompt y/o imágenes, y la generación inteligente de insumos sugeridos (de stock y nuevos), listos para que Producción los revise".

- Pantalla: `/orders/new` (ADR 0028). Cliente Caja Piura. Ítem 1 con foto de un polo (`backend/seed/images/products/UNI-POD-01.jpg`): Claude describe la prenda y cae la frase; se escribe la cantidad y se reconoce el producto con sus insumos. Ítem 2 por texto: "100 polos escolares blancos con logo bordado". Se ve el chip verde del producto del catálogo y, en un producto nuevo, el chip ámbar con los insumos marcados "Nuevo". El resumen a la derecha suma insumos y compara la fecha contra la ruta crítica. "Crear orden" y el detalle con la ficha técnica.
- Frases: "Comercial escribe la orden como la pide el cliente, o sube una foto." / "Cada línea se reconoce sola: producto del catálogo o producto nuevo." / "Los insumos salen de la receta: los que hay en stock y los que hay que crear." / "La orden nace con ficha técnica y fecha estimada por ruta crítica."

### 3. Producción revisa y ajusta por prompt (Producción)

Idea: "Producción revisa órdenes y confirma si todo bien, o las ajusta por prompt".

- Pantalla: `/orders` como Producción, chip "Por revisar". Abrir la orden nueva. En la ficha técnica, escribir en "Ajustar la ficha técnica con una instrucción" algo como "agrega 2 botones por polo y cambia la tela a drill" → "Proponer" → se ve el diff → "Aplicar" (ADR 0029). Luego "Aprobar y abastecer" con su modal de confirmación.
- Frases: "Producción ve primero lo que tiene que revisar." / "Si algo no cuadra, lo corrige con una instrucción en lenguaje natural." / "Al aprobar, los insumos entran a 'por pedir'."

### 4. Inventario, reserva y pedido en lote (Producción, luego Gerente)

Idea: "se va reservando inventario o creando ítems nuevos para pedir en batch; Producción hace el pedido en batch cuando lo requiera y el agente empieza a interactuar con los proveedores en representación del Gerente".

- Pantalla: `/inventory` como Producción: columnas stock, reservado por órdenes abiertas, disponible, y el chip "Por pedir" con las cantidades acumuladas entre órdenes. "Pedir todo" → modal → "N pedidos generados · esperando aprobación del Gerente" (ADR 0025, 0031). Cambiar al Gerente: en el Monitor aparece la decisión de asignación; "Aprobar" y sale el toast "Enviando por WhatsApp…" y "Enviado a {proveedor}". En `/purchase-orders/<id>` se ve el primer mensaje del agente con el precio de referencia y la fecha, en el estilo del Gerente.
- Frases: "Cada orden reserva stock y acumula lo que falta." / "Producción pide todo en un lote cuando le conviene." / "El agente escribe a cada proveedor con el precio de referencia, en el estilo del Gerente." / "Nunca pide cotización: propone precio y fecha."

### 5. Proveedores medidos y matching por histórico (Gerente)

Idea: "ahora medimos a los proveedores y podemos hacer matching automático sin necesidad de aprobación del Gerente, en base a histórico".

- Pantalla: `/suppliers` como Gerente: tarjetas con cumplimiento, calidad, precio y carga (ADR 0030). Abrir la decisión de asignación en el Monitor → "Cambiar proveedor": el ranking con barras por criterio y la justificación. Aprobar.
- Frases: "Cada entrega califica al proveedor: cumplimiento, calidad, precio y carga." / "El sistema propone el mejor proveedor para cada pedido y explica por qué." / "El Gerente aprueba con un clic, o cambia; el cambio alimenta el histórico."
- Pendiente: hoy el matching siempre crea una decisión que el Gerente aprueba (ADR 0025). El modo "sin aprobación" no existe. Si se quiere mostrar, hace falta un ADR nuevo con un interruptor en Configuración ("Aprobar solo cuando el proveedor sugerido tiene menos de X % de cumplimiento" o "aprobar en automático"). Mientras no esté, la frase del video dice "con un clic", no "sin aprobación".

### 6. WhatsApp en vivo y el dashboard se actualiza (Gerente)

Idea: "vista de WhatsApp en donde con cada actualización del proveedor con el agente, la información en el dashboard se va actualizando".

- Pantalla: dos ventanas lado a lado. Izquierda: `/purchase-orders/<pedido>` con "Chat con el proveedor" y la línea de tiempo. Derecha: `/simulator?present=1` (o el celular de Valeria). El proveedor acepta la fecha → el pedido pasa a "Confirmado" y la fecha comprometida aparece en la ruta crítica de la orden. Reporta avance con foto ("ya van 400") → la barra de avance y la foto aparecen en el pedido. Mostrar también la página pública `/report/<token>` desde el celular (ADR 0024).
- Frases: "El proveedor responde por WhatsApp; el agente entiende y actualiza el pedido." / "Fecha comprometida, avance y fotos aparecen en el dashboard sin que nadie los copie." / "Si es decisión de jefe (precio, términos), el agente no decide: escala al Gerente."

### 7. Cancelación y avisos por rol, sin datos sensibles (Gerente y Comercial)

Idea: "si un pedido se aplaza o se cancela, toda la empresa es notificada, sin que se filtren datos sensibles como precios o contactos de proveedores; solo el Gerente tiene acceso".

- Pantalla: dos ventanas. El taller escribe "Jefe, no voy a poder terminar. Se me malogró la máquina." El agente responde y escala. En el Gerente: tarjeta "Redistribución" con 400 hechas / 600 repartidas entre dos talleres, fecha y costo antes → después (ADR 0024). En Comercial: su asistente avisa "orden en peligro" con la fecha nueva, sin precios ni proveedor; en el detalle de la orden ve avance, fotos y estado, nunca el chat.
- Frases: "Un taller cancela a mitad del pedido." / "El sistema reparte lo que falta entre otros talleres y recalcula fecha, costo y ruta." / "Comercial y Producción se enteran al instante; precios y contactos solo los ve el Gerente."

### 8. Rutas y flota en vivo (Producción)

Idea: "el planeamiento de rutas también".

- Pantalla: `/routes` como Producción. Planificar: "Volver a planificar el día" reparte las órdenes listas entre Furgón 1, Camioneta 2 y Moto 3 según capacidad; la que no cabe queda "Sin asignar" con su motivo y se pasa a mañana. En vivo: "Iniciar ruta" del Furgón 1, "Simular", pantalla completa, la primera parada pasa a "Entregada" (ADR 0026; tiempos en `docs/demo/guion-visual.md`, paso 6b).
- Frases: "Producción arma el día de entregas en un clic, por vehículo y capacidad." / "Rutas multiparada por Piura, desde la planta." / "Cada vehículo se ve en vivo y cada entrega se marca sola."

### Lo que no entra en este video

- Seguimiento proactivo configurable (ADR 0027) y pausa del agente (ADR 0030): se mencionan en el pitch, no se graban.
- Seguimiento a pedido desde el asistente de Comercial (paso 9b del guion): si sobra tiempo, cabe como escena 6b con `06b-avance-a-pedido.mp4`.

## Grabación

- `cd video && node record.mjs` graba las 8 escenas en unos 6 minutos (la 7 espera al agente y a los avisos). Orden interno: 1, 2, 3, 4, 5, 6, 7, 7b (tarjeta de redistribución, se pega al final de la 7) y 8.
- Las tomas crudas quedan en `video/out/raw/` (gitignored). La escena 2 crea una orden nueva y la 3 la ajusta; la 7 cancela PT-0038 por el contacto simulado de Confecciones del Norte; la 8 deja la simulación del Furgón detenida.
- Después de grabar: `seed_demo --reset-chats` y reiniciar worker y beat (lo coordina el orquestador).
- Formato de salida: mp4 H.264 a 1920×1080 y 30 fps, sin audio. La voz en off, si se graba, va como `video/public/voiceover.mp3` (pendiente de decidir).

## Versión de 2 minutos para el pitch (`Demo2min`)

Pedido de Oscar (11/10, por el orquestador): el demo dentro de la presentación dura 2 minutos o menos. `video/src/Demo2min.tsx` arma esa versión con las mismas 8 grabaciones: una tarjeta de título de 2 s por feature (número, una línea, kit de marca) y después solo los momentos donde se ve la feature, como cortes limpios a velocidad real (las esperas del sistema se saltan cortando, sin cámara rápida). Cada tarjeta y cada corte es un nodo editable en Remotion Studio (`Demo2min`, carpeta "Demo2min-Elementos").

| # | Feature | Tarjeta | Cortes | Total |
|---|---|---|---|---|
| 1 | Puesta en marcha: Claude, WhatsApp y estilo | 2,0 s | 8,0 s | 10,0 s |
| 2 | Orden mágica: texto o foto, con insumos | 2,0 s | 17,5 s | 19,5 s |
| 3 | Producción ajusta la ficha por prompt | 2,0 s | 12,0 s | 14,0 s |
| 4 | Pedido en lote: el agente escribe solo | 2,0 s | 11,2 s | 13,2 s |
| 5 | Proveedores medidos, matching por histórico | 2,0 s | 9,5 s | 11,5 s |
| 6 | WhatsApp en vivo, dashboard al día | 2,0 s | 15,8 s | 17,8 s |
| 7 | Cancelación: avisos a todos, sin precios | 2,0 s | 11,5 s | 13,5 s |
| 8 | Rutas y flota en vivo | 2,0 s | 18,0 s | 20,0 s |
| | **Total** | 16,0 s | 103,5 s | **119,5 s** |

Render: `npx remotion render Demo2min out/demo-2min.mp4` (1080p, 30 fps, sin audio). Va también en `docs/demo/pitch/demo-2min.mp4` (gitignored), que reproduce `docs/demo/pitch/index.html`: el deck de Kenji con una slide nueva entre "Después" y el cierre; en esa slide la primera tecla o clic arranca el video y la siguiente pasa de slide.

## Exportar

Video completo (4 min 49 s, subtítulos y transiciones): en `video/`, `npx remotion render CorpotexFeatures out/corpotex-features.mp4`, o el botón "Render" de Remotion Studio. Detalle en `video/README.md`.
