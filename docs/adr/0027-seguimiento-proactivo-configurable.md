# 0027. Seguimiento proactivo configurable por el Gerente: ventana, modos y decisión del agente

- Fecha: 2026-10-11 (01:00)
- Estado: aceptada (pedido de Oscar, 11/10 00:55). Reemplaza el seguimiento por `Supplier.follow_up_every_hours` (cada N horas desde el último contacto). Lo implementan backend, agente, personalidad y disenador.

## Contexto

Hoy el agente le escribe al proveedor cada `follow_up_every_hours` horas: es un ritmo fijo por proveedor que no depende del plazo del pedido. Un pedido de 7 días y uno de 14 reciben el mismo ritmo, y uno de horas recibe el primer seguimiento cuando ya venció. Además, la única ventana horaria es `QUIET_HOURS` del `.env`.

En la entrevista, Corpotex contó que llaman "al día 3 o 4 de un plazo de 5" y que a algunos proveedores les incomoda que insistan. Oscar pide tres cosas:

- Que el Gerente configure desde Configuración el rango horario del seguimiento.
- Que haya tres modos: mínimo, balanceado y alto.
- Que el agente decida, según el modo y las interacciones, si escribe: como máximo una vez al día, más un recordatorio si el proveedor no responde.

## Decisión

### 1. Configuración (Gerente)

Nuevos campos en `Config` (singleton), con estos valores por defecto:

| Campo | Defecto | Qué es |
|---|---|---|
| `follow_up_mode` | `balanced` | `minimal`, `balanced` o `high` |
| `follow_up_window_start` / `follow_up_window_end` | 09:00 / 18:00 | Rango horario (hora de Lima) en que el agente puede hacer seguimiento |
| `follow_up_weekdays` | `[0,1,2,3,4,5]` | Días hábiles (0 = lunes). El domingo queda fuera |

Por proveedor: `Supplier.follow_up_mode`, que puede ir vacío. Vacío usa el modo general. Si no, lo reemplaza, por ejemplo con `minimal` para un proveedor al que le molesta que insistan. `follow_up_every_hours` queda en la base y deja de usarse.

API: `GET/PATCH /api/settings/follow-up/` es solo para el Gerente. `GET /api/settings/follow-up/preview/` muestra el plan de hoy: `[{supplier, purchase_orders: [code], at, kind: checkpoint | reminder, reason}]`.

### 2. Cuándo se considera escribir (código, determinista)

- **Un mensaje por proveedor y por día.** Si un proveedor tiene varios pedidos abiertos, un solo mensaje los cubre, como ya hace el lote del turno. A eso se suma, como mucho, un recordatorio.
- **Puntos de control proporcionales al plazo.** El plazo va de la confirmación, o la aprobación, a `committed_on`:

| | Mínimo | Balanceado | Alto |
|---|---|---|---|
| Puntos de control | 50 % del plazo y la víspera de la entrega | 30 %, 60 % y 85 % del plazo, más la víspera | todos los días hábiles |
| Pedido de 10 días | días 5 y 9 | días 3, 6, 8 y 9 | días 1 a 9 |
| Se salta el punto de control si… | el proveedor escribió o reportó avance desde el punto anterior | reportó avance en las últimas 24 h y va a ritmo | (nunca se salta; el mensaje es corto) |
| Recordatorio si no responde | al día siguiente; ocupa el seguimiento de ese día | a las 4 h, el mismo día, dentro de la ventana | a las 2 h |
| Alerta "sin avance" al Gerente | sin respuesta al recordatorio | sin respuesta al recordatorio | sin respuesta al recordatorio |

- **Siempre se considera escribir**, en cualquier modo, en tres casos: la entrega es hoy o mañana y no está confirmada; el avance va atrasado, porque las unidades del último reporte están más de 15 puntos por debajo de lo esperado en línea recta; o no hay ningún reporte desde la confirmación y ya pasó el 30 % del plazo.
- **Ventana.** Solo dentro de la ventana y en los días hábiles. Para que no parezca un bot, el primer mensaje del día se reparte en la primera hora de la ventana, con un desfase fijo por proveedor.
- **Pedido del día.** Un pedido más corto que un día, como el ejemplo de 7 o 14 horas, entra como "entrega hoy". `committed_on` sigue siendo una fecha sin hora: agregar hora queda fuera de este ADR.
- **Estado por pedido.** `PurchaseOrder` suma `last_follow_up_on` (date), `awaiting_reply_since` (datetime) y `reminded_at` (datetime). Cualquier mensaje del proveedor en su conversación limpia `awaiting_reply_since` en sus pedidos abiertos. `next_follow_up_at` pasa a ser la próxima oportunidad calculada.
- **Tick.** El `tick`, que corre cada minuto, evalúa y encola un turno `follow_up` por conversación con `kind` (`checkpoint` o `reminder`) y `reason`. Ninguna otra parte encola turnos de seguimiento.
- **Las otras escrituras proactivas no cambian.** El primer contacto tras la aprobación y la respuesta a una decisión del Gerente siguen como hoy, con `QUIET_HOURS` del `.env`: el Gerente está actuando en ese momento.

### 3. El agente decide

El turno `follow_up` le pasa al agente el contexto, y este decide si escribe:

- **Contexto.** El modo, el `kind` y la `reason` ("punto de control del 60 %", "víspera de entrega", "sin respuesta desde las 10:05") y, por cada pedido, la fecha comprometida y el avance esperado contra el reportado. También le pasa cuándo fue el último mensaje del proveedor y el último del agente, si hay una decisión pendiente y las notas del proveedor.
- **Herramienta nueva** `skip_follow_up(reason)`. La usa cuando escribir no aporta: el proveedor ya avisó algo que cubre la pregunta, hay una decisión del Gerente pendiente que el proveedor espera, o escribió hace poco. El motivo queda en el pedido (`follow_up_note`) y el Gerente lo ve en el detalle.
- **Texto, en el estilo del Gerente.** El punto de control va en una o dos líneas, pregunta por el avance concreto y pide foto si hace falta. El recordatorio es más corto que el original, no reclama y no repite la pregunta completa. Cada turno manda como máximo un mensaje.
- **Al enviar**, se fijan `awaiting_reply_since` y `last_follow_up_on`. Al saltar, se fija solo `last_follow_up_on`: aun así cuenta como el seguimiento del día.

### 4. Configuración en el dashboard

`/settings` deja de ser el stepper del onboarding y pasa a ser **Configuración con un submenú** (lista vertical en escritorio, pestañas con scroll horizontal en móvil):

1. **Seguimiento**, la nueva, que se abre por defecto:
   - Modo como control segmentado (Mínimo, Balanceado, Alto), con una línea de explicación y una mini línea de tiempo de ejemplo para un pedido de 10 días.
   - Rango horario con dos campos de hora; "Desde" tiene que ser menor que "Hasta" y la ventana dura al menos 2 h.
   - Días como chips L M X J V S D.
   - Botón Guardar con confirmación.
   - Abajo, "Plan de hoy", que viene del preview.
2. **Estilo**, la página actual de `/settings/style`, sin cambios.
3. **Conexiones**: Claude y WhatsApp, las páginas actuales.
4. **Proveedores**: el acceso a `/suppliers`. En la ficha del proveedor se suma "Seguimiento: usar el general / Mínimo / Balanceado / Alto".

El stepper de 4 pasos pasa a ser un resumen compacto arriba del submenú, por ejemplo "Puesta en marcha 4/4", que solo se despliega si falta algún paso. Se mantienen las URLs actuales (`/settings/style`, `/settings/claude`, `/settings/whatsapp`), las redirecciones del PR #93 y `/settings/claude?reconnect=1`.

### 5. Seed y demo

- Valores por defecto: ventana 09:00–18:00, de lunes a sábado, modo balanceado.
- El pitch es el domingo 11/10, y el domingo queda fuera de los días hábiles. Así ningún seguimiento automático le escribe a Valeria durante la demo. Para el pedido del número real, el seed además deja `last_follow_up_on = hoy`, por si alguien activa el domingo.
- Las escenas del guion no dependen de seguimientos programados. Si Oscar quiere mostrarlo en vivo, se agrega el domingo en Configuración y se usa un proveedor del simulador.

## Consecuencias

- El tick deja de usar `follow_up_every_hours`. La alerta `stalled_purchase_order` pasa a salir cuando el proveedor no responde al recordatorio.
- Hay un turno de Claude más por proveedor y por día, en los días con punto de control. Con pocos proveedores el costo es despreciable.
- Tareas y responsables en `docs/planning.md` (S1 a S4). Congelamiento a las 04:30: si S1 y S2 no están en verde, el seguimiento sigue como hoy.
