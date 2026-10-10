# 0005. Postgres en Docker

- Estado: aceptada
- Fecha: 2026-10-10

## Contexto

El webhook, el worker del agente y el reloj acelerado escriben en la BD a la vez.

## Decisión

Postgres levantado con docker compose.

## Consecuencias

- Sin bloqueos por escrituras concurrentes, a diferencia de SQLite.
- Cada integrante levanta su propia BD local; la data de demo se carga con un script de seed.
- docker compose también levanta `redis`, `celery-worker` y `celery-beat` (ADR 0018).
