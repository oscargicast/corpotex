# Glosario: nombres en español → código en inglés

El código va en inglés y la documentación en español (ADR 0014). Esta tabla traduce los nombres que usan los docs a los que van en el código.

## Apps y modelos

Los campos y valores de `choices` de cada modelo están en la sección "Equivalencias" de [`docs/backend/modelo-de-datos.md`](backend/modelo-de-datos.md).

| App (docs → código) | Modelos |
|---|---|
| core → `core` | `User`, `Config` (Configuracion), `Brand` (Marca), `Customer` (Cliente), `Product` (Producto), `Material` (Insumo), `ProductMaterial` (ProductoInsumo), `OnboardingStyle` (estilo del onboarding) |
| proveedores → `suppliers` | `Supplier` (Proveedor), `Rate` (Tarifa). La calificación son los campos `rating_*` de `PurchaseOrder` |
| operaciones → `operations` | `Order` (Orden), `OrderItem`, `Requirement` (Requerimiento), `PurchaseOrder` (Pedido), `PurchaseOrderItem`, `ProgressReport` (Avance), `Delivery` (Entrega), `Payment` (Pago). Sin `Route` ni `RouteStop` (ADR 0015) |
| mensajeria → `messaging` | `AllowedNumber` (NumeroPermitido), `Conversation`, `Message`, `Turn` (Turno) |
| gerencia → `manager` | `Decision`, `Alert` (Alerta) |
| agente → `agent` | sin modelos |

### Campos que aparecen en los ADR

| Docs | Código |
|---|---|
| `Proveedor.telefono_whatsapp` | eliminado: los celulares viven en `AllowedNumber.phone` (ADR 0016) |
| `Proveedor.notas`, `es_propio` | `Supplier.notes`, `is_in_house` |
| `Configuracion.estilo_gerente`, `duraciones_etapa` | `User.style_md` y `User.style_refreshed_at` (ADR 0019), `Config.stage_durations` |
| usuario dueño del número del agente | `Config.agent_user` |
| historial del estilo | `StyleVersion` {user, style_md, notes_snapshot, source: `onboarding` \| `daily` \| `template` \| `manual` \| `rollback`, changelog, created_at} (ADR 0019) |
| `Conversacion.sesion_agente` | `Conversation.agent_session` |
| número de la conversación | `Conversation.allowed_number` (reemplaza teléfono y proveedor) |
| conversación donde se negocia un pedido | `PurchaseOrder.conversation` |
| conversación del asistente | `Conversation` con `channel=dashboard` y `user` (una por usuario) |
| acción pendiente de confirmar en el asistente | `Conversation.pending_action` |
| tarjeta de acción y vista del usuario en el chat | `Message.action`, `Message.context`; `author=user` (la API lo devuelve como `role`) |
| `Decision.pedidos`, `comunicada_en` | `Decision.purchase_orders` (M2M), `communicated_at` |
| `Mensaje.turno`, `autor=gerente` | `Message.turn`, `author=manager` |
| `Turno` {conversacion, motivo, decision, estado, intentos, error, disponible_en} | `Turn` {conversation, reason, decision, status, attempts, error, available_at} |
| `Pedido.fecha_limite_interna` | `PurchaseOrder.internal_due_on` |
| roles Gerente, Comercial, Producción | `manager`, `sales`, `production` (los grupos del admin se ven en español) |
| `estado_display` | `status_display` (el valor va en español) |

### Valores de estados

| Docs | Código |
|---|---|
| motivo del turno | `Turn.reason`: `message`, `decision`, `follow_up`, `purchase_order_approved` |
| estado del turno | `Turn.status`: `pending`, `running`, `done`, `error` |
| estado del pedido | `PurchaseOrder.status`: `suggested`, `approved`, `negotiating`, `confirmed`, `in_progress`, `delivered`, `declined_by_supplier`, `cancelled_by_supplier`, `cancelled` |
| estado de la orden | `Order.status`: `registered`, `broken_down`, `confirmed`, `sourcing`, `in_production`, `ready`, `delivered`, `cancelled` |
| riesgo de la orden | `Order.risk`: `ok`, `at_risk`, `in_danger` |
| tipo de decisión | `Decision.kind`: `approve_assignment`, `price`, `terms`, `other` |
| estado de la decisión | `Decision.status`: `pending`, `approved`, `rejected`, `supplier_changed`, `cancelled` |
| tipo de alerta | `Alert.kind`: `stalled_purchase_order`, `delay`, `order_in_danger`, `no_response`, `payment_due`, `instance_down`, `no_channel` (sin_canal), `turn_failed` |

## Servicios

| Docs | Código |
|---|---|
| `reloj.ahora()` | `clock.now()` |
| `encolar_turno` | `enqueue_turn(conversation, reason, decision=None)` |
| `tomar_siguiente_turno`, `LoteTurno` | `claim_next_turn() -> TurnBatch` {turn, message_ids, decision_ids, follow_up_purchase_order_ids, new_purchase_order_ids} |
| `terminar_turno` | `finish_turn(batch, session_id, error=None)` |
| recuperar turnos colgados | `recover_stuck_turns()` |
| `estado_turno` | `turn_state(batch)` |
| historial | `message_history(conversation, limit=20)` |
| enviar por WhatsApp | `messaging.services.send_text(conversation, text, turn)`; cliente HTTP: `evolution.send_text(phone, text)` |
| pedido de una conversación | `purchase_order_for_conversation(conversation, code)` |
| aprobar pedidos | `approve_purchase_orders` |
| `confirmar_pedido` | `confirm_purchase_order` |
| `registrar_avance` | `record_progress(..., message_id=None)` |
| `cancelar_por_proveedor` | `cancel_by_supplier` |
| `redistribuir` | `redistribute` |
| `crear_decision` | `create_decision(*, kind, purchase_orders, summary, detail, conversation=None, order=None)` |
| `resolver_decision` | `resolve_decision` |
| desglose, confirmar orden, matching, ruta crítica | `break_down_order`, `confirm_order`, `match_requirements`, `compute_critical_path` |
| monitor, tick, extracción de estilo | `run_monitor`, `tick`, `run_style_extraction` |
| refresco diario del estilo | `refresh_style` (tarea de Celery beat, 03:00 de Lima, ADR 0019) |
| aprobar y restaurar estilo | `approve_style`, `restore_style_version` |
| chequeo de rol | `require_role(actor, *roles)` → `PermissionDenied` |
| servicios con `actor` del asistente | `register_order`, `record_delivery`, `mark_payment_paid`, `acknowledge_alert`, `set_clock` (además `confirm_order`, `record_progress`, `resolve_decision`) |
| asistente | `record_assistant_action`, `assistant_turn_state` |
| turno en Celery | `agent.tasks.run_turn(conversation_id)` |
| regla de jefe y errores | `ManagerApprovalRequired`, `NumberNotAllowed`, `SendFailed`, `ForeignPurchaseOrder` |

## API (todas las rutas con barra final)

| Docs | Código |
|---|---|
| `/api/gerente/pendientes/` | `/api/manager/pending/` |
| `/api/gerente/decisiones/<id>/` | `/api/manager/decisions/<id>/` |
| `/api/reloj/` | `/api/clock/` |
| `/api/ordenes/` | `/api/orders/` (y `<id>/confirm/`) |
| `/api/pedidos/` | `/api/purchase-orders/` |
| `/api/pagos/<id>/pagar/` | `/api/payments/<id>/pay/` |
| `/api/alertas/<id>/reconocer/` | `/api/alerts/<id>/acknowledge/` |
| `/api/proveedores/` | `/api/suppliers/` (y `import/`, `self-register/`) |
| simulador | `/api/simulator/contacts/`, `/api/simulator/messages/` |
| mensajes de una conversación | `/api/conversations/<id>/messages/?after=` |
| `/api/onboarding/estilo/` | `/api/onboarding/style/` |
| asistente | `/api/assistant/messages/` (GET con `?after=`, POST), `/api/assistant/reset/` |
| cuenta de Claude (solo Gerente, ADR 0022) | `/api/settings/claude/start/`, `exchange/`, `status/`, `disconnect/`, `set-key/` |
| historial del estilo | `/api/style/versions/`, `/api/style/versions/<id>/`, `<id>/restore/`; P1: `/api/style/refresh/` |
| entregas y avances de un pedido | `/api/purchase-orders/<id>/deliveries/`, `/api/purchase-orders/<id>/progress/` |
| sin cambio | `/webhooks/evolution/<secret>/`, `/api/auth/*`, `/api/monitor/`, `/api/onboarding/whatsapp/*`, `/api/schema/` |
| decisión `{accion: aprobar \| rechazar \| cambiar_proveedor, proveedor_id?, pedido_id?, nota?}` | `{action: approve \| reject \| change_supplier, supplier_id?, purchase_order_id?, note?, channel?}` |

## Agente (`backend/agent/`)

| Español (docs) | Código |
|---|---|
| app `agente` | `agent` (`backend/agent/`) |
| carpeta de runtime `backend/.agente/` | `backend/.agent/` (gitignored) |
| worker del agente | tareas de Celery en `agent/` (ADR 0018) |
| loop de turnos | `agent/worker.py`, `run_turn` |
| adaptadores de canal (`canales.py`) | `agent/channels.py`: `EvolutionChannel`, `SimulatorChannel` |
| tick del reloj | `agent/tick.py` |
| reglas de jefe (`reglas.py`) | `agent/rules.py`, `RULES` |
| helper del SDK aislado | `agent/sdk.py`: `isolated_options()`, `complete()` |
| modelo del agente | env `AGENT_MODEL` |

### Tools

El modelo las ve como `mcp__corpotex__<nombre>`.

| Español (docs) | Código |
|---|---|
| `enviar_mensaje` | `send_message` |
| `confirmar_pedido` | `confirm_purchase_order` |
| `registrar_avance` | `record_progress` |
| `reportar_cancelacion` | `report_cancellation` |
| `escalar_gerente` | `escalate_to_manager` |
| `leer_historial` | `read_history` |

Nombres fijados por el orquestador para que todas las sesiones coincidan: Orden = `Order`, Pedido = `PurchaseOrder`, Proveedor = `Supplier`, Gerente = `manager`.

## Asistente del dashboard (ADR 0017)

Un chat en el dashboard para cada usuario, con tools según su rol (`manager`, `sales`, `production`). Usa el mismo `agent/sdk.py` y la misma cola de turnos que el agente de WhatsApp. Tools por rol (las de escritura piden confirmación en código, con `pending_action`):

| Rol | Tools |
|---|---|
| todos | `list_orders`, `get_order`, `list_purchase_orders`, `get_purchase_order`, `list_alerts` |
| `manager` | `list_pending`, `list_suppliers`, `get_supplier`, `resolve_decision`, `acknowledge_alert`, `mark_payment_paid`, `set_clock` |
| `sales` | `find_client`, `register_order` |
| `production` | `confirm_order`, `record_delivery`, `record_progress` |

Prompt: `build_assistant_prompt(conversation, batch, with_history=False)` en `agent/persona/assistant.py`.

## Personalidad (`backend/agent/persona/`)

Armado del prompt del agente y extracción de estilo. El texto que lee el modelo (prompts y etiquetas XML) va en español; el Python, en inglés.

| Español (docs) | Código |
|---|---|
| carpeta `personalidad/` | `backend/agent/persona/` |
| `construir_prompt(conversacion, lote)` | `build_prompt(conversation, batch, with_history=False) -> (system, turn_message)` |
| extracción de estilo | `extract_style(chats, since, on_progress=None, manager_names=())` |
| parser del export `.txt` | `parse_whatsapp_export(content, manager_author, since, supplier_id=None, supplier_name=None)` |
| contexto del turno | `persona/context.py` |
| plantilla base del estilo (el "BOSS.md" vive en `User.style_md`) | `persona/templates/style.base.md` |
| escenarios de prueba | `persona/scenarios.yaml` |
| modelos de la extracción | `STYLE_ANALYSIS_MODEL` (`sonnet`), `STYLE_BOSS_MODEL` (`opus`) |

### Contrato del paso Estilo

| Español (docs) | Código |
|---|---|
| `/api/onboarding/estilo/` | `/api/onboarding/style/` |
| `extraer/`, `importar-txt/`, `base/`, `aprobar/` | `extract/`, `import-txt/`, `template/`, `approve/` |
| desde, proveedores, archivo, autor del Gerente | `since`, `supplier_ids`, `file`, `manager_author` |
| estado, paso, mensajes leídos, notas, aprobado en | `status`, `step`, `messages_read`, `notes`, `approved_at` |
| estados generales | `not_started`, `extracting`, `draft`, `approved`, `error` |
| estados por proveedor | `pending`, `reading`, `analyzing`, `done`, `no_phone`, `no_chat`, `not_allowed`, `error` |

## Dashboard (rutas de Next.js)

Cada ruta usa el nombre de su modelo.

| Vista (docs) | URL |
|---|---|
| Monitor (inicio) | `/` |
| Login | `/login` |
| Órdenes y detalle | `/orders`, `/orders/[id]` |
| Pedidos y detalle (insumo, taller, terminado) | `/purchase-orders`, `/purchase-orders/[id]` |
| Proveedores y talleres | `/suppliers`, `/suppliers/[id]` |
| Simulador de chat | `/simulator` |
| Asistente (pantalla completa en móvil) | `/assistant` |
| Historial del estilo (solo Gerente) | `/style` |
| Onboarding (4 pasos) | `/onboarding/claude`, `/onboarding/whatsapp`, `/onboarding/suppliers`, `/onboarding/style` |
| Configuración: cuenta de Claude (solo Gerente) | `/settings/claude` |
| Autoregistro público | `/supplier-signup` |
