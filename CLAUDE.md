# CORPOTEX · Reto 7 Piura Innova

Hackathon Piura Innova, 10 y 11 de octubre de 2026. Reto 7: gestión inteligente de talleres y proveedores. Empresa: Corpotex (UNICRACK SPORT & UNIFORMS). Equipo: Oscar, Valeria, Nesky, Freddy.

El repo arranca vacío. Prioridad: que la demo funcione el domingo; velocidad antes que pulido.

Stack: backend Django + Django REST Framework, frontend Next.js, Postgres, agente con Claude Agent SDK; Jev (TypeSafe AI, `TYPESAFE_API_KEY`) para clasificar ítems de órdenes contra catálogo e inventario (ADR 0025 C). Monorepo: `backend/`, `frontend/`, `infra/`, `docs/` (ADR 0008); todo levanta con `docker compose up` desde la raíz (ADR 0023). Las decisiones de arquitectura están en `docs/adr/`; cada decisión nueva va como un ADR numerado ahí. URL pública: `https://corpotex.oscargicast.com` (ADR 0006).

## Convenciones

- Código en inglés: identificadores, comentarios, docstrings, endpoints y claves JSON (ADR 0014). Equivalencias español → inglés en `docs/glosario.md`.
- En español: la documentación y los textos para personas (dashboard, admin, WhatsApp, el texto del estilo del Gerente).
- Commits y PRs sin créditos de Claude: sin `Co-Authored-By: Claude …` ni "Generated with Claude Code" (decisión de Oscar).
- Tests con pytest en cada PR de backend (`docker compose exec web pytest -q` en verde antes de mergear); `pnpm typecheck` y `pnpm build` en cada PR de frontend. Sin verde no se mergea.

## Qué construimos

Un agente que lleva la orden del cliente hasta que el proveedor entrega. Habla por WhatsApp desde el número del Gerente y con su estilo (solo texto; clonar la voz es fase 2).

Roles (usar estos en el producto y la data, no nombres reales):

- **Gerente**: dueño. Controla proveedores, precios y pagos. Ve todo. Atiende pendientes y alertas en el dashboard.
- **Comercial**: registra órdenes de clientes.
- **Producción**: revisa y confirma el desglose.

Cada rol tiene en el dashboard un asistente (chat) con tools y permisos propios de su rol (ADR 0017). El asistente también avisa solo, en ese chat, de pedidos retrasados u órdenes en peligro, a cada rol lo que le toca (ADR 0020). Los datos de demo salen de `python manage.py seed_demo` con fixtures en `backend/seed/` (ADR 0021).

Usuarios: uno sembrado por rol. Usuarios, roles y contraseñas se gestionan desde el admin de Django; el resto del dashboard es Next.js.

Flujo:

0. Estilo del Gerente: perfil de cómo escribe, sacado de sus chats.
1. Comercial registra la orden en `/orders/new` (o llega por API): cada línea en texto libre se reconoce mientras escribe (Jev contra catálogo e inventario, Claude para lo nuevo) y la orden nace desglosada contra inventario (ADR 0028, 11/10 02:05). "Simular orden de Comercial" salió de la lista de órdenes; el componente sigue en el simulador.
2. Producción revisa y confirma.
3. Los requerimientos de insumos quedan "por pedir" y se acumulan entre órdenes; Producción o el Gerente generan el pedido consolidado cuando lo ven necesario (el asistente lo sugiere a tiempo). Los pedidos de taller y producto terminado salen por orden. El sistema asigna proveedor por histórico (cumplimiento, precio, carga). El Gerente confirma o cambia antes de aprobar; el cambio alimenta el histórico (ADR 0025).
4. El agente conversa con el proveedor, responde dudas y acuerda fecha. Si se cumplen todos los términos, cierra el pedido solo y actualiza pedido y orden. Si es decisión de jefe (precio, términos), no decide: crea una decisión pendiente para el Gerente y espera.
5. Seguimiento: cualquier retraso o riesgo al plazo crea una alerta para el Gerente y marca la orden en peligro. El seguimiento proactivo al proveedor lo configura el Gerente en Configuración → Seguimiento (modo mínimo, balanceado o alto, rango horario y días hábiles); el agente escribe como máximo una vez por proveedor y día, más un recordatorio si no responde, y decide si vale la pena escribir (ADR 0027).

Por debajo: tres tipos de pedido (insumo, taller, terminado), fecha de la orden por ruta crítica, permisos por rol (el equipo ve el nombre del proveedor, no su número; las conversaciones con proveedores y el simulador solo los ve el Gerente: Comercial y Producción ven avances, fotos, estado y fechas, nunca el texto de WhatsApp. Pedido de Oscar, 10/10 20:50).

### Dashboard (5 vistas más Configuración del Gerente)

1. Órdenes de clientes.
2. Pedidos a proveedores y talleres.
3. Monitor con alertas (retrasos, órdenes en peligro).
4. Proveedores de insumos y talleres: solo el Gerente tiene permisos.
5. Inventario de insumos (stock, reservado por órdenes abiertas, disponible, y el estado "Por pedir" con "Pedir todo" que genera los pedidos consolidados): Gerente y Producción; Comercial no lo ve (pedido de Oscar, 10/10 20:40). La vista aparte "Por pedir" se quitó el 11/10 01:30: era solo un filtro de inventario.

### Onboarding (ADR 0011)

Vive en la pestaña "Configuración" del Gerente (`/settings`; desde el 10/10 23:45 no hay pestañas aparte de Onboarding ni de Estilo, pedido de Oscar). Puesta en marcha de 3 pasos (Proveedores salió del resumen el 11/10 01:55: se cargan en su propia pestaña `/suppliers`, celular opcional): conectar la cuenta de Claude (ADR 0022), conectar WhatsApp (QR y webhook de la instancia `corpotex`) y extraer el estilo del Gerente de sus chats con proveedores (el "BOSS.md": un texto que se guarda en `User.style_md`, con historial en `StyleVersion`, ADR 0019). Solo se leen los chats de celulares de proveedores registrados.

## Demo

- Comercial crea la orden en vivo en `/orders/new` (paso 3 del guion); la API del sistema de Comercial sigue existiendo. Envío real por Evolution API con el número de Oscar.
- Sin reloj simulado (decisión de Oscar, 10/10 21:40): `core.clock` queda con factor 1 (hora real) y el dashboard no muestra reloj; las escenas con retraso salen del seed (fechas relativas a hoy).
- Usuarios de rol del seed con contraseña `SEED_USERS_PASSWORD` del `.env`; ninguno es staff del admin (solo el superuser `admin`).
- Escena que pide el jurado: un taller cancela a mitad del pedido y el sistema redistribuye y recalcula fecha, costo y ruta (ADR 0024).
- Clientes en la data: Caja Piura, colegios de Piura, AIDER, PIQA.
- Por WhatsApp solo hay un proveedor real: Valeria (`51906746241`, constante en el seed, activo en la allowlist). El Gerente escribe desde el número de Oscar (`51907898162`). Los demás proveedores van por el simulador. Oscar no puede ser proveedor: es su propio número.
- Plan B: simulador de chat si falla el wifi, y video de respaldo (lo graba Oscar a mano, decisión 10/10 21:00; el guion y el script de grabación están en `docs/demo/guion-visual.md`).
- En vivo no se muestra el QR ni se corre la extracción de estilo: el onboarding se muestra ya hecho, con el estilo del Gerente ya extraído y aprobado (ADR 0011).
- Orden del guion: el paso Estilo (mostrar el borrador y aprobar) va ANTES de la escena de WhatsApp. El bot usa el último estilo aprobado; si se aprueba después, el bot habla con el perfil base.
- Dato de dolor para el pitch: al proveedor le dan 5 días cuando al cliente le prometieron 10, y aun así hay pedidos que nadie revisa hasta el día 9.

## Criterios del reto

- Móvil y escritorio.
- Talleres reportan avance con fotos (WhatsApp, simulador y página pública `/report/<token>`, ADR 0024).
- Registro de talleres: especialidad, capacidad, precios, calidad, cumplimiento, rating automático por entrega.
- Matching multicriterio con justificación.
- Dividir un pedido grande entre talleres.
- CRUD de órdenes por rol: Comercial y Gerente crean y editan; Producción solo confirma desgloses, mueve estados de pedidos y genera pedidos consolidados (ADR 0025).
- Seguimiento de pedidos y pagos (adelantos, saldos): P0 (ADR 0024).
- Rutas multiparada en mapa de Piura: entregas de órdenes a clientes, salen de la planta principal; no hay recojos en proveedores (ADR 0024: `Route`, `plan_route`, Leaflet; corrección de Oscar 10/10 23:35).
- Flota y rutas en vivo (ADR 0026, pedido de Oscar 10/10 23:15): varios vehículos con capacidad; Producción planifica el día por vehículo (`plan_day`) y reprograma órdenes listas a otras fechas; posición de cada vehículo por API (muestra guardada cada 5 min), SSE al dashboard con checkboxes por vehículo, simulador y mapa a pantalla completa. Lo implementa la sesión `rutas`.
- Sugerir nuevos proveedores: autoregistro P0 y tool `suggest_suppliers` con búsqueda web P1 (ADR 0024).

## Dominio (entrevista a Corpotex, 10/10)

- 3 marcas: UNICRACK (uniformes escolares, incluye deportivos), NEXO (ropa de trabajo de alto rendimiento) y Línea Médica Corpotex.
- 1 taller propio y 3-4 talleres externos (solo costura, cuando la planta se satura; reciben todo cortado, bordado y estampado). Bordado y sublimado 100% en planta. A veces tercerizan productos completos.
- ~10 proveedores de insumos, mayoría de Lima: telas (algodón 20/1, 30/1), botones, cierres, cuellos y puños (rib). Un proveedor clave de México (10 años) da la mejor calidad y precio, pero los deja en standby y no tiene alternativa.
- Una orden de cliente se reparte entre varios proveedores (tela, botones, cierre, cuello). El Gerente junta los pedidos de las 3 marcas en uno por proveedor. Cuando llega todo: corte, confección, bordado/sublimado.
- Plazos: proveedor 15 días para 5000+ unidades, 7-10 días para pedidos chicos. Producción propia ~7 días.
- No cotizan: usan precios históricos 2024-2025; solo cotizan productos nuevos. Regla para el agente: en el primer contacto propone el precio de referencia y la fecha, nunca pide cotización al proveedor.
- Pagos: 50% adelanto y 50% a la entrega, casi todo por Yape, a veces transferencia y factura. Solo paga el Gerente; si se atrasa, el proveedor deja de atenderlos.
- Seguimiento: llamada o WhatsApp al día 3-4 de un plazo de 5, nada queda anotado. Al proveedor le incomoda que insistan (varía por proveedor). Caso real: un pedido de 10 días sin avance que nadie notó.
- Su sistema de producción nuevo genera orden/ficha técnica en PDF o Excel (código, cliente, RUC, marca, estado, responsable, fechas de emisión y entrega, precios, detalle, imagen; estados corte/sublimado/bordado/costura). Poca adopción. No tenemos PDFs de ejemplo: los datos de órdenes se inventan en el seed.
- Rutas: los proveedores de Lima envían por la agencia Sullana Express y ellos recogen en Piura.
- Campañas: Unicrack de enero a marzo, Corpotex de agosto a octubre.

## Arquitectura del agente (ADR 0004)

El Agent SDK es Claude Code como librería: corre el binario de Claude Code por pipes (stream-json), como `mano`, con las tools en Python. No se usa API key: la cuenta de Claude la conecta el Gerente una vez desde `/settings/claude` (ADR 0022) y todos los agentes la comparten.

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
- Tunnel: `cloudflared tunnel --config infra/cloudflared/config.yml run corpotex`. Cloudflare bloquea con 403 (error 1010) los user agents genéricos de Python (`Python-urllib`, `python-requests`) tanto en `evolution.oscargicast.com` como en `corpotex.oscargicast.com`: todo cliente manda un `User-Agent` propio (`EvolutionClient` ya lo hace); al probar con curl o Python, pasar uno. En la laptop de Oscar pasar siempre `--config`: el config global de cloudflared apunta a otro tunnel (`turbo`) y `route dns` sin él enruta al tunnel equivocado.
- Enviar: `POST /message/sendText/corpotex` con el token de la instancia (`EVOLUTION_INSTANCE_TOKEN`). El backend no usa la API key global ni toca `personal-whatsapp` (ADR 0010).
- Recibir (decidido 10/10): segunda instancia `corpotex`, vinculada al número de Oscar por QR como otro dispositivo, con su propio webhook `MESSAGES_UPSERT` hacia nuestro backend. Recibe todos los mensajes del número, así que la allowlist se filtra en nuestro código. Webhook: `https://corpotex.oscargicast.com/webhooks/evolution/<EVOLUTION_WEBHOOK_SECRET>/` (secreto en `.env`; la vista de Django lo valida), solo `MESSAGES_UPSERT`, con base64 para recibir las fotos en el payload.

Reglas de la instancia `personal-whatsapp` (número de Oscar):

- No reemplazar el webhook actual (un flujo personal de Oscar, en uso) sin ok explícito de Oscar.
- Nunca hacer logout ni borrar la instancia: re-vincular pide QR desde el teléfono de Oscar.
- `groupsIgnore` se queda en `true`.
- El bot solo responde a una allowlist de números del equipo; nunca a familia ni a contactos de Turbo.
- El pod se reinicia seguido; después de cualquier reinicio, verificar que la instancia vuelva a `open`.

## Planning

El plan por fases, con responsables, dependencias e hitos, está en `docs/planning.md`. Resumen: sábado tarde cimientos; sábado noche datos y flujo principal; madrugada asistente, onboarding y monitor; domingo mañana integración, ensayo y video.

## Pendiente de decidir (preguntar a Oscar)

- Reparto del equipo.

El pitch lo maneja Oscar. La agenda real está en `docs/planning.md`. El guion del chat de rol con la proveedora real está en `docs/guion-chat-de-rol.md`.

Estado de Evolution (10/10, 17:25): instancia `corpotex` `open`, webhook configurado (solo `MESSAGES_UPSERT`, base64), `groupsIgnore=true`, y el service token de Cloudflare Access en `.env` probado contra la API.

Más contexto: Kenji lo guarda en el trick hackathon-retos; pedirlo con `/kenji`.
