# 0011. Onboarding: WhatsApp, proveedores y estilo del Gerente

- Estado: aceptada
- Fecha: 2026-10-10

## Contexto

Oscar pidió un onboarding que deje listo el sistema para una empresa nueva: conectar WhatsApp, cargar proveedores y sacar de las conversaciones pasadas cómo se comunica el Gerente con ellos, en un `BOSS.md` con ejemplos que usa el agente.

Lo verificado el 10/10 desde el pod de Evolution, leyendo solo conteos:

- Evolution guarda el historial (`DATABASE_SAVE_DATA_HISTORIC=true`, `DATABASE_SAVE_DATA_NEW_MESSAGE=true`). La instancia `corpotex` ya tiene 38 616 mensajes sincronizados al vincularse, aunque `syncFullHistory` esté apagado.
- `POST /chat/findMessages/{instancia}` filtra por `remoteJid`, así que se puede leer solo el chat de un proveedor.
- Responden `GET /instance/connectionState/{instancia}`, `GET /webhook/find/{instancia}` y `GET /settings/find/{instancia}`. `GET /instance/connect/{instancia}` (QR), `POST /webhook/set/{instancia}` y `POST /settings/set/{instancia}` son parte de la API v2, pero no se probaron porque cambian el estado.

## Decisión

El onboarding es un asistente en el tablero, solo para el Gerente, con 3 pasos:

1. **WhatsApp:** muestra el estado de la instancia de `EVOLUTION_INSTANCE`, el QR para vincularla si no está `open`, y un botón que configura el webhook (URL con secreto, solo `MESSAGES_UPSERT`, base64) y los settings (ignorar grupos; rechazar llamadas, marcar como leído y sincronizar historial apagados). Usa el token de la instancia a través del service token de Cloudflare Access. No crea, desconecta ni borra instancias, y nunca toca `personal-whatsapp`. Si el service token no está listo, el paso se marca como hecho fuera de línea y muestra el estado leído.
2. **Proveedores:** alta o importación de proveedores. El celular es opcional y se guarda en `AllowedNumber` (ADR 0016). Sin él no se puede extraer el estilo con ese proveedor.
3. **Estilo del Gerente:** por cada proveedor con celular, el backend lee de Evolution solo ese chat. Con los mensajes del Gerente y las respuestas del proveedor como contexto, genera el `BOSS.md` (perfil y ejemplos anonimizados) y notas por proveedor (tú o usted, si le incomoda que insistan, horario). El Gerente lo revisa y edita antes de aprobarlo. Lo aprobado se guarda en el campo de estilo del usuario y en una fila de `StyleVersion` (ADR 0019), y las notas en `Supplier.notes`. Alternativas: subir el export `.txt` de un chat, o partir del perfil base escrito desde la entrevista.

## Ajustes acordados entre sesiones (10/10)

- Allowlist: dar de alta un proveedor con celular crea su `AllowedNumber` inactivo. El Gerente lo activa a mano, y tanto la extracción como el agente usan solo números activos. Así un número mal cargado no recibe respuestas ni se lee su chat.
- Lectura: solo el JID del proveedor (y su `@lid`), nunca grupos; obligatorio un "leer desde" (en la demo, 10/10); solo texto y captions; como mucho los últimos 300 mensajes; sin los mensajes que mandó el agente.
- Anonimización en código antes de llamar a un modelo. El borrador se guarda ya anonimizado.
- Extracción con Claude Code (Agent SDK sin tools, ADR 0013): un llamado por proveedor y uno final que arma el `BOSS.md`. Corre como tarea de Celery en la cola `style` (ADR 0018).
- Contrato: recurso único `/api/onboarding/style/` (GET/PUT) con `extract/`, `import-txt/`, `template/` y `approve/`. `extract/` y `template/` reemplazan el borrador; `import-txt/` lo actualiza de forma incremental (si no hay borrador, parte de la plantilla), así varios chats se acumulan.
- Antes de la demo, no en vivo: `extract` (el proveedor real), `import-txt` por cada fixture sintético y la revisión. En vivo solo se muestra el borrador listo y se aprueba.
- Los mensajes que el Gerente escribe a mano a un proveedor se guardan como `author=manager`, sin disparar turno, para regenerar el estilo y para el historial del agente.
- Demo: el paso 1 se muestra ya hecho. Proyectar un QR en vivo permitiría que cualquiera lo escanee.
- Demo: la extracción de estilo no corre en vivo. El `BOSS.md` va precalculado y aprobado, y el paso 3 se muestra con el borrador ya generado. La extracción en acción va en el video de respaldo. Motivo: comparte los límites de la suscripción con el bot (ADR 0013), y un 429 en medio de un turno se notaría en WhatsApp.

## Consecuencias

- Privacidad: la instancia tiene todas las conversaciones del número de Oscar, familia incluida. La extracción lee únicamente los chats de los celulares de proveedores registrados. Los mensajes crudos no se guardan en la BD ni en el repo; al repo entra solo una plantilla base de `BOSS.md`.
- Baileys puede identificar un chat con `@lid` en vez del número: la búsqueda tiene que probar también el campo alterno.
- En la demo, los proveedores con celular son miembros del equipo, así que el estilo sale de sus chats con Oscar. Hace falta su consentimiento.
- El paso 1 depende del service token de Cloudflare Access; sin él, la conexión de WhatsApp se asume hecha antes y fuera de línea.
- Responsables: `personalidad` (extracción y formato de `BOSS.md`), `backend` (endpoints de onboarding y lectura de Evolution), `disenador` (pantallas del asistente).
