# 0001. Recibir WhatsApp con una segunda instancia de Evolution API

- Estado: aceptada
- Fecha: 2026-10-10

## Contexto

El agente necesita recibir los mensajes de los proveedores (evento `MESSAGES_UPSERT`). La instancia `personal-whatsapp` (número de Oscar) tiene un solo webhook y está ocupado por un flujo personal de n8n (`pepita`), que sigue en uso y no se puede reemplazar sin ok de Oscar.

## Decisión

Crear la instancia `corpotex` (Baileys), vinculada al número de Oscar por QR como un dispositivo más, con su propio webhook hacia nuestro backend.

## Consecuencias

- `corpotex` recibe todos los mensajes del número, familia incluida. El backend filtra por allowlist antes de responder.
- `personal-whatsapp` sigue mandando todo a pepita. Si Valeria hace de proveedor en la demo, sus mensajes también llegan a pepita: revisar que ese flujo no reaccione.
- Settings de `corpotex`: ignorar grupos activado; rechazar llamadas, marcar como leído y sincronizar historial apagados.
- Usa uno de los dispositivos vinculados de la cuenta de WhatsApp de Oscar.

## Alternativas descartadas

- Websocket en `personal-whatsapp`: requiere `WEBSOCKET_ENABLED` por Argo CD y reiniciar el pod, que ya es inestable.
- n8n reenvía a nuestro backend: acopla la demo a n8n.
- Pisar el webhook durante el hackathon: rompe pepita.
