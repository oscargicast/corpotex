# 0010. Cola de turnos del agente y aislamiento del Agent SDK

- Estado: aceptada (ajustada el 10/10 con lo que acordaron `backend` y `agente`). Worker y tick corren en Celery (ADR 0018).
- Fecha: 2026-10-10

## Contexto

El agente corre un turno por conversación. Hay turnos que no nacen de un mensaje del proveedor: la decisión del Gerente resuelta, el seguimiento del reloj y el primer mensaje al proveedor de un pedido recién aprobado (incluida la redistribución). Los proveedores suelen mandar varios mensajes seguidos, y pueden llegar varias causas a la vez para la misma conversación.

## Decisión

### Cola

- Tabla `messaging.Turn` {conversation, reason: message | decision | follow_up | purchase_order_approved, decision?, status, attempts, error, available_at}. `reason` y `decision` son solo rastro: el porqué del turno sale del estado fresco.
- Un único servicio `enqueue_turn(conversation, reason, decision=None)` en `messaging/services.py`, que llaman el webhook, la resolución de decisiones, la aprobación de pedidos y el tick. Si ya hay un turno pendiente, lo reutiliza. Cada llamado dispara la tarea del turno en Celery con `countdown` hasta `available_at` (ADR 0018).
- `available_at`: cada mensaje nuevo lo corre a ahora + 5 s, con tope de 20 s desde que se creó el turno, en hora real. El worker solo toma turnos disponibles y nunca duerme dentro de un turno.
- `claim_next_turn()` toma con `select_for_update(skip_locked=True)`, excluye las conversaciones con un turno en curso y devuelve un `TurnBatch` {turn, message_ids, decision_ids, follow_up_purchase_order_ids, new_purchase_order_ids}: los mensajes sin procesar, las decisiones resueltas sin comunicar (`Decision.communicated_at`), los pedidos aprobados sin contactar y los seguimientos vencidos. `turn_state(batch)` arma con eso el estado fresco del turno.
- `finish_turn(batch, session_id, error)` marca solo lo que vino en el lote; lo que llegue mientras corre lo toma el turno siguiente. `session_id` se guarda aunque el turno falle, y `Message.turn` registra qué envió cada turno, para que un reintento no repita envíos.
- Al arrancar, el worker devuelve a pendiente los turnos que quedaron en curso. Al tercer error, el turno pasa a `error` y crea una `Alert`.
- Una `Decision` de asignación aprueba un lote de pedidos (`Decision.purchase_orders`, M2M). Al resolverla se encola un turno en la conversación de cada proveedor aprobado; si la conversación no existe, se crea.

### Agente

- Una sesión del Agent SDK por conversación (`Conversation.agent_session`). Si se pierde el archivo de sesión, el turno abre una nueva con los últimos 20 mensajes de la BD.
- Tools atadas a la conversación del turno: `send_message(text)`, `confirm_purchase_order`, `record_progress`, `report_cancellation`, `escalate_to_manager`, `read_history`. El modelo nunca ve ni elige teléfonos. Las tools llaman a `backend/*/services.py`, nunca a los modelos.
- Las reglas de jefe están en código: `confirm_purchase_order` rechaza un precio sobre la `Rate` o una fecha pasada de `internal_due_on`, y le pide al modelo que escale.
- Prompt: `build_prompt(conversation, batch)` de `personalidad` devuelve `(system, turn_message)`. El `system` es estable por conversación (reglas de `agent/rules.py`, más el estilo y las notas del proveedor) para no romper el caché ni el hilo; todo lo que cambia va en `turn_message`.
- El adaptador de canal vuelve a chequear la allowlist antes de enviar, como segundo filtro. Las respuestas salen por la instancia `corpotex` con su token; el backend no usa la API key global.
- Aislamiento del SDK: `tools=[]` más `allowed_tools` con las nuestras, `permission_mode="dontAsk"`, `setting_sources=[]`, `CLAUDE_CONFIG_DIR` y cwd propios en `backend/.agent/` (gitignored) y `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`. Así el agente no lee el `CLAUDE.md` del repo ni la config personal de Oscar. La credencial (`CLAUDE_CODE_OAUTH_TOKEN`, ADR 0013) se pasa por `env=`.
- El tick del reloj es una tarea de Celery que beat lanza cada ~10 s reales (ADR 0018): encola seguimientos y llama al monitor.

## Consecuencias

- Juntar causas en un turno nunca pierde nada, porque el turno lee el estado fresco.
- Los eventos de sistema no ensucian el historial del chat que ve el tablero.
- Cada turno deja rastro de reintentos y errores.
- Un proveedor sin celular no se puede contactar: su pedido aprobado queda en `approved` con una `Alert` `no_channel`.
