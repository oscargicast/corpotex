# 0020. El asistente del dashboard avisa de forma proactiva

- Estado: aceptada (decisión de Oscar). Amplía el ADR 0017.
- Fecha: 2026-10-10

## Contexto

El asistente del dashboard (ADR 0017) solo responde cuando el usuario le escribe. Oscar quiere que avise solo cuando un pedido se retrasa o está por retrasarse, y que cada rol reciba lo que le toca: Gerente, Comercial o Producción.

## Decisión

El asistente escribe primero cuando el monitor detecta un retraso. Cada aviso llega al chat del asistente de los usuarios del rol que corresponde y aparece como un mensaje del asistente, sin que el usuario haya preguntado.

### Qué dispara un aviso y a quién

| Situación (la detecta `run_monitor` en el tick) | Alerta | Gerente | Comercial | Producción |
|---|---|---|---|---|
| Pedido sin avance ni respuesta pasado el plazo de consulta (`next_follow_up_at`) | `stalled_purchase_order` | sí | | sí si es de taller |
| El proveedor no responde tras los reintentos del agente | `no_response` | sí | | |
| Fecha comprometida vencida sin entrega | `delay` | sí | | sí |
| La fecha estimada de la orden pasa la prometida al cliente (`Order.risk = in_danger`) | `order_in_danger` | sí | sí | sí |
| Pedido aprobado sin canal | `no_channel` | sí | | |
| Pago vencido | `payment_due` | sí | | |
| Decisión pendiente sin resolver más de N horas simuladas | `decision_pending` (nueva) | sí | | |

La regla general: el Gerente recibe todo; Comercial solo lo que afecta la fecha prometida al cliente; Producción lo que afecta sus talleres y el desglose.

### Cómo se entrega

- `run_monitor` crea o actualiza la `Alert` (sin duplicar: una abierta por `(kind, purchase_order)` u `(kind, order)`).
- Por cada `Alert` nueva, `notify_roles(alert)` encola un `Turn` con `reason = alert` en la conversación de asistente de cada usuario activo del rol destinatario. Si el usuario no tiene conversación, se crea.
- El turno del asistente recibe la alerta en el estado del turno y redacta el aviso en el idioma y nivel de detalle del rol (sin precios ni teléfonos para Comercial y Producción), con un link a la orden o al pedido. Es un mensaje del asistente con `Message.action = {kind: "alert", alert_ids}` para que el dashboard lo muestre como tarjeta con sus links.
- Sin repetición: una alerta se avisa una vez por usuario (`AlertNotification` {alert, user, turn, sent_at}). Si la alerta sigue abierta al día siguiente simulado, se vuelve a avisar solo al Gerente.
- En el dashboard, el panel del asistente muestra un punto o contador cuando hay avisos sin leer (`Conversation.unread_count` o se calcula con `Message.read_at`). En móvil, la pestaña del asistente lleva el contador.
- El usuario puede responder al aviso en el mismo chat ("¿qué taller es?", "cámbialo de proveedor") y el asistente sigue con sus tools de rol (ADR 0017).

### El turno de aviso (diseño de `personalidad`)

- El turno recibe las alertas como datos estructurados ya filtrados por rol, nunca `Alert.text`. Al Gerente le llegan proveedor, cifras y el resumen de la decisión; a Comercial, orden, cliente, fecha prometida y fecha estimada nueva, con la causa genérica; a Producción, pedido, taller, avance N/M y fecha límite.
- Formato: por alerta, una línea en negrita con qué pasó, y una o dos líneas con desde cuándo y qué puede hacer ese rol. El texto no lleva URLs: la tarjeta del dashboard pone el link a partir de `alert_ids`, así el modelo no puede escribir una ruta mal. Avisos de 2 a 3 líneas, generados con `effort=low`. Varias alertas: un solo mensaje con lista, críticas primero, como mucho 5, y "y N más en el Monitor".
- Un aviso nunca ejecuta ni deja preparada una acción: no llama tools que escriben ni termina en "(sí/no)". La confirmación de dos pasos empieza recién cuando el usuario contesta, así un "sí" por reflejo no reasigna nada. Tampoco necesita tools de lectura: es un solo llamado al modelo.
- Pruebas en `scenarios.yaml` con chequeos por regex de lo que debe y no debe aparecer (por ejemplo, Comercial sin precios, teléfonos ni notas; el nombre del taller sí lo ve, ADR 0017).

### Qué no hace

- No manda WhatsApp ni correo: solo el chat del asistente y el Monitor.
- No decide nada solo: un aviso al Gerente puede sugerir "¿quieres que reasigne?", pero la acción sigue pidiendo confirmación.

## Consecuencias

- `Turn.reason` suma `alert`; `Alert.kind` suma `decision_pending`; tabla nueva `AlertNotification`; `Message.read_at`.
- Cada alerta cuesta un turno de asistente por usuario destinatario. Con el reloj acelerado, el monitor puede generar muchas en poco tiempo: `run_monitor` agrupa las alertas de un mismo tick en un solo turno por usuario.
- En la demo, la escena del taller que cancela produce avisos distintos para el Gerente (decisión pendiente, con el detalle) y para Comercial (orden en peligro, con la nueva fecha estimada). Eso muestra los permisos por rol sin explicarlos.
