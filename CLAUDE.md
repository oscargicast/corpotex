# CORPOTEX · Reto 7 Piura Innova

Hackathon Piura Innova, 10 y 11 de octubre de 2026. Reto 7: gestión inteligente de talleres y proveedores. Empresa: Corpotex (UNICRACK SPORT & UNIFORMS). Equipo: Oscar, Valeria, Nesky, Freddy.

El repo arranca vacío. Prioridad: que la demo funcione el domingo; velocidad antes que pulido.

Stack: backend Django + Django REST Framework, frontend Next.js, Postgres, agente con Claude Agent SDK. Monorepo: `backend/`, `frontend/`, `infra/`, `docs/` (ADR 0008). Las decisiones de arquitectura están en `docs/adr/`; cada decisión nueva va como un ADR numerado ahí. URL pública: `https://corpotex.oscargicast.com` (ADR 0006).

## Convenciones

- Código en inglés: identificadores, comentarios, docstrings, endpoints y claves JSON (ADR 0014). Equivalencias español → inglés en `docs/glosario.md`.
- En español: la documentación y los textos para personas (tablero, admin, WhatsApp, `BOSS.md`).

## Qué construimos

Un agente que lleva la orden del cliente hasta que el proveedor entrega. Habla por WhatsApp desde el número del Gerente y con su estilo (solo texto; clonar la voz es fase 2).

Roles (usar estos en el producto y la data, no nombres reales):

- **Gerente**: dueño. Controla proveedores, precios y pagos. Ve todo. Atiende pendientes y alertas en el tablero.
- **Comercial**: registra órdenes de clientes.
- **Producción**: revisa y confirma el desglose.

Cada rol tiene en el tablero un asistente (chat) con tools y permisos propios de su rol (ADR 0017).

Usuarios: uno sembrado por rol. Usuarios, roles y contraseñas se gestionan desde el admin de Django; el resto del tablero es Next.js.

Flujo:

0. Estilo del Gerente: perfil de cómo escribe, sacado de sus chats.
1. Comercial registra la orden; llega por API y el agente la desglosa contra inventario.
2. Producción revisa y confirma.
3. El sistema asigna proveedor por histórico (cumplimiento, precio, carga). El Gerente confirma o cambia antes de aprobar; el cambio alimenta el histórico.
4. El agente conversa con el proveedor, responde dudas y acuerda fecha. Si se cumplen todos los términos, cierra el pedido solo y actualiza pedido y orden. Si es decisión de jefe (precio, términos), no decide: crea una decisión pendiente para el Gerente y espera.
5. Seguimiento: cualquier retraso o riesgo al plazo crea una alerta para el Gerente y marca la orden en peligro.

Por debajo: tres tipos de pedido (insumo, taller, terminado), fecha de la orden por ruta crítica, permisos por rol (el equipo ve el nombre del proveedor, no su número).

### Tablero (4 vistas)

1. Órdenes de clientes.
2. Pedidos a proveedores y talleres.
3. Monitor con alertas (retrasos, órdenes en peligro).
4. Proveedores de insumos y talleres: solo el Gerente tiene permisos.

### Onboarding (ADR 0011)

Asistente del Gerente con 3 pasos: conectar WhatsApp (QR y webhook de la instancia `corpotex`), cargar proveedores (celular opcional) y extraer el estilo del Gerente de sus chats con proveedores a un `BOSS.md`. Solo se leen los chats de celulares de proveedores registrados.

## Demo

- API simulada del sistema de Comercial, envío real por Evolution API con el número de Oscar, reloj acelerado.
- Escena que pide el jurado: un taller cancela a mitad del pedido y el sistema redistribuye y recalcula fecha y costo. La ruta no se implementa (ADR 0015).
- Clientes en la data: Caja Piura, colegios de Piura, AIDER, PIQA.
- Miembros del equipo hacen de talleres/proveedores por WhatsApp.
- Plan B: simulador de chat si falla el wifi, y video de respaldo.
- En vivo no se muestra el QR ni se corre la extracción de estilo: el onboarding se muestra ya hecho, con el `BOSS.md` precalculado (ADR 0011).
- Dato de dolor para el pitch: al proveedor le dan 5 días cuando al cliente le prometieron 10, y aun así hay pedidos que nadie revisa hasta el día 9.

## Criterios del reto

- Móvil y escritorio.
- Talleres reportan avance con fotos (web o WhatsApp).
- Registro de talleres: especialidad, capacidad, precios, calidad, cumplimiento, rating automático por entrega.
- Matching multicriterio con justificación.
- Dividir un pedido grande entre talleres.
- Seguimiento de pedidos y pagos (adelantos, saldos).
- Rutas multiparada en mapa de Piura: fuera de alcance (ADR 0015).
- Sugerir nuevos proveedores (fuentes externas o autoregistro).

## Dominio (entrevista a Corpotex, 10/10)

- 3 marcas: UNICRACK (uniformes escolares, incluye deportivos), NEXO (ropa de trabajo de alto rendimiento) y Línea Médica Corpotex.
- 1 taller propio y 3-4 talleres externos (solo costura, cuando la planta se satura; reciben todo cortado, bordado y estampado). Bordado y sublimado 100% en planta. A veces tercerizan productos completos.
- ~10 proveedores de insumos, mayoría de Lima: telas (algodón 20/1, 30/1), botones, cierres, cuellos y puños (rib). Un proveedor clave de México (10 años) da la mejor calidad y precio, pero los deja en standby y no tiene alternativa.
- Una orden de cliente se reparte entre varios proveedores (tela, botones, cierre, cuello). El Gerente junta los pedidos de las 3 marcas en uno por proveedor. Cuando llega todo: corte, confección, bordado/sublimado.
- Plazos: proveedor 15 días para 5000+ unidades, 7-10 días para pedidos chicos. Producción propia ~7 días.
- No cotizan: usan precios históricos 2024-2025; solo cotizan productos nuevos.
- Pagos: 50% adelanto y 50% a la entrega, casi todo por Yape, a veces transferencia y factura. Solo paga el Gerente; si se atrasa, el proveedor deja de atenderlos.
- Seguimiento: llamada o WhatsApp al día 3-4 de un plazo de 5, nada queda anotado. Al proveedor le incomoda que insistan (varía por proveedor). Caso real: un pedido de 10 días sin avance que nadie notó.
- Su sistema de producción nuevo genera orden/ficha técnica en PDF o Excel (código, cliente, RUC, marca, estado, responsable, fechas de emisión y entrega, precios, detalle, imagen; estados corte/sublimado/bordado/costura). Poca adopción. Comercial va a mandar PDFs de ejemplo.
- Rutas: los proveedores de Lima envían por la agencia Sullana Express y ellos recogen en Piura.
- Campañas: Unicrack de enero a marzo, Corpotex de agosto a octubre.

## Arquitectura del agente (ADR 0004; detalle de Kenji, sin verificar contra la doc)

Claude Agent SDK en Python, por eventos:

1. Cada mensaje de un proveedor (evento `MESSAGES_UPSERT` de Evolution) dispara un turno. Filtrar `fromMe`. Cola por chat para no correr dos turnos en paralelo.
2. Una sesión por pedido/chat, reanudada en cada turno. Cada turno lee estado fresco de la API (pedido, orden, proveedor); la sesión solo guarda el hilo.
3. Tools: leer historial de WhatsApp, enviar por Evolution, actualizar pedido/orden, leer proveedor, escalar al Gerente.
4. Cron con reloj acelerado para seguimientos y alertas.

Autenticación: suscripción de Claude de Oscar con `CLAUDE_CODE_OAUTH_TOKEN` (ADR 0013); para entregar a Corpotex, API key.

## WhatsApp: Evolution API

- Evolution API v2.3.7 en el mac-mini (SSH `macmini`), k3s, namespace `automation`, deploy `evolution-api`, gestionado por Argo CD: los cambios de env van por el repo de infra, no con `kubectl edit`.
- `https://evolution.oscargicast.com` está detrás de Cloudflare Access (curl externo da 302). Probar desde dentro del pod con `kubectl exec`.
- API key global en `.secret` y token de la instancia `corpotex` en `.env` (ambos gitignored). Nunca commitearlos ni imprimirlos.
- Tunnel: `cloudflared tunnel --config infra/cloudflared/config.yml run corpotex`. En la laptop de Oscar pasar siempre `--config`: el config global de cloudflared apunta a otro tunnel (`turbo`) y `route dns` sin él enruta al tunnel equivocado.
- Enviar: `POST /message/sendText/corpotex` con el token de la instancia (`EVOLUTION_INSTANCE_TOKEN`). El backend no usa la API key global ni toca `personal-whatsapp` (ADR 0010).
- Recibir (decidido 10/10): segunda instancia `corpotex`, vinculada al número de Oscar por QR como otro dispositivo, con su propio webhook `MESSAGES_UPSERT` hacia nuestro backend. Recibe todos los mensajes del número, así que la allowlist se filtra en nuestro código. Webhook: `https://corpotex.oscargicast.com/webhooks/evolution/<EVOLUTION_WEBHOOK_SECRET>/` (secreto en `.env`; la vista de Django lo valida), solo `MESSAGES_UPSERT`, con base64 para recibir las fotos en el payload.

Reglas de la instancia `personal-whatsapp` (número de Oscar):

- No reemplazar el webhook actual (un flujo personal de n8n, `pepita`, en uso) sin ok explícito de Oscar.
- Nunca hacer logout ni borrar la instancia: re-vincular pide QR desde el teléfono de Oscar.
- `groupsIgnore` se queda en `true`.
- El bot solo responde a una allowlist de números del equipo; nunca a familia ni a contactos de Turbo.
- El pod se reinicia seguido; después de cualquier reinicio, verificar que la instancia vuelva a `open`.

## Planning

- Sábado tarde: data demo, motor (desglose, asignación, ruta crítica), estilo del Gerente.
- Sábado noche: agente WhatsApp, tablero, reloj acelerado.
- Domingo mañana: prueba punta a punta x2, video de respaldo, pitch, ensayo cronometrado.

## Pendiente de decidir (preguntar a Oscar)

- Números de la allowlist.
- Reparto del equipo.
- Hora de entrega, formato del pitch y pesos de los criterios.
- PDFs de ejemplo de Comercial (todavía no llegan).

Más contexto: Kenji lo guarda en el trick hackathon-retos; pedirlo con `/kenji`.
