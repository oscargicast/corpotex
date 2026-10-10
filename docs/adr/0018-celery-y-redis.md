# 0018. Celery con Redis para el trabajo en segundo plano

- Estado: aceptada (decisión de Oscar). Ajusta el ADR 0010 en dónde corre el worker.
- Fecha: 2026-10-10

## Contexto

Oscar pidió que el estilo se refresque todos los días con Celery beat, con Redis y con servicios separados en docker compose. El ADR 0010 tenía un worker propio (un management command) para turnos y tick. Mantener los dos sería tener dos sistemas de fondo.

## Decisión

- docker compose, en la raíz del repo (ADR 0023), levanta `postgres`, `redis`, `web` (Django en `0.0.0.0:8000`), `celery-worker`, `celery-beat` y `frontend` (Next.js).
- Un solo `celery-worker` (pool prefork; gevent y eventlet rompen los subprocesos) con las colas `turns`, `periodic` y `style`, `-c 5`, `acks_late` y `prefetch=1`. Los turnos tienen `soft_time_limit` de ~180 s. La cola `style` corre una tarea a la vez gracias a un lock en la BD. Si en las pruebas el tick se atrasa detrás de los turnos (con el reloj acelerado, un minuto es un día), se separa un contenedor `celery-periodic`.
- La tarea `agent.tasks.run_turn(conversation_id)` es idempotente: toma el turno con `claim_next_turn(conversation_id)` y, si no hay ninguno, termina. Al terminar, `finish_turn` vuelve a encolarla si quedó otro turno pendiente en esa conversación.
- El worker corre siempre en el contenedor, con el volumen de `CLAUDE_CONFIG_DIR` y el cwd fijos, porque el archivo de sesión depende de la ruta. Nunca se mezcla con corridas nativas en la Mac ni se monta el `.venv` de la Mac.
- Todo el trabajo en segundo plano corre en Celery:
  - Los turnos del agente de WhatsApp y del asistente del dashboard (ADR 0017): `enqueue_turn` dispara una tarea con `countdown` hasta `available_at`. La tabla `Turn` sigue siendo la fuente de verdad de la cola y de la exclusividad por conversación (`select_for_update(skip_locked=True)`). Así un reintento o una tarea duplicada no corre dos turnos a la vez.
  - El tick: beat cada ~10 s (seguimientos y monitor).
  - La extracción de estilo del onboarding y el refresco diario (ADR 0019): cola `style`, con concurrencia 1.
- El schedule es estático en settings. No hace falta django-celery-beat.
- El contenedor del worker monta el volumen `agent-home` como `CLAUDE_CONFIG_DIR`: ahí viven la credencial de Claude (ADR 0022) y las sesiones que el Agent SDK reanuda.

## Consecuencias

- Desaparece el comando `run_agent`; las piezas de `agent/` pasan a ser tareas de Celery. `agente` y `backend` confirman el detalle.
- Más servicios que levantar en la laptop. El beat cada 10 s también relanza los turnos vencidos (por si Redis perdió una tarea) y pasa a `error` los que llevan más de 10 min en `running`.
- Si Redis o el worker se caen, se paran los turnos. Por eso, tras un reinicio, la recuperación del ADR 0010 sigue haciéndose desde la tabla `Turn`.
