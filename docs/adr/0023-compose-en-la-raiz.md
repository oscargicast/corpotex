# 0023. Todo levanta con docker compose desde la raíz

- Estado: aceptada (decisión de Oscar). Ajusta el ADR 0008 (compose vivía en `infra/`) y el ADR 0018 (Next.js corría en el host).
- Fecha: 2026-10-10

## Contexto

Oscar quiere las carpetas `backend/` y `frontend/` en la raíz y que todo el entorno de desarrollo se levante con un solo `docker compose up` desde la raíz del repo, con las últimas versiones estables de cada paquete.

## Decisión

`docker-compose.yml` en la raíz del repo levanta todo:

| Servicio | Imagen | Puerto | Para qué |
|---|---|---|---|
| `postgres` | `postgres:18-alpine` | 5432 | base de datos |
| `redis` | `redis:8-alpine` | 6379 | broker de Celery |
| `web` | `backend/Dockerfile` | 8000 | Django + DRF (`runserver 0.0.0.0:8000`) |
| `celery-worker` | la misma imagen | | colas `turns`, `periodic`, `style` (ADR 0018) |
| `celery-beat` | la misma imagen | | tick y `refresh_style` |
| `frontend` | `frontend/Dockerfile` | 3000 | Next.js en modo dev |

- `web`, `celery-worker` y `celery-beat` montan `./backend` para recarga en caliente; `frontend` monta `./frontend` con `node_modules` en un volumen propio.
- Volumen `agent-home` compartido por `web` y los dos de Celery: ahí viven `CLAUDE_CONFIG_DIR` y la credencial de Claude (ADR 0022).
- `web` corre `migrate` al arrancar; `seed_demo` se corre a mano (`docker compose exec web python manage.py seed_demo`).
- `.env` en la raíz lo leen todos los servicios (`env_file`). `POSTGRES_PASSWORD` sale de ahí.
- Los puertos se publican solo en `127.0.0.1`: en el wifi del evento nadie más entra a Postgres, Redis, Django o Next.js. El tunnel corre en el host y llega igual a `localhost`.
- `infra/` queda solo para el tunnel de Cloudflare. Nada se instala en el host salvo Docker y `cloudflared`.

Versiones (estables al 10/10/2026): Python 3.13, Django 6.1, DRF 3.18, Celery 5.6, redis 8.1 (cliente), psycopg 3.3, drf-spectacular 0.30, claude-agent-sdk 0.2.165, pydantic 2.14, django-environ 0.14, django-cors-headers 4.9; Node 24 LTS, pnpm 12, Next.js 16.4, React 19.3, TypeScript 7.0, Tailwind 4.3, SWR 2.5. Gestores: `uv` en backend, `pnpm` en frontend.

## Consecuencias

- Un solo comando para cualquier integrante: `cp .env.example .env && docker compose up`.
- El tunnel apunta a `localhost:8000` y `localhost:3000`, que ahora son puertos publicados por compose. No cambia.
- El worker de Celery necesita el CLI de Claude Code dentro de la imagen; el wheel del SDK lo trae, pero se verifica en el primer build (si no, se agrega Node a la imagen de backend).
- Python 3.13 y no 3.14: el SDK y Celery están probados en 3.13; 3.14 salió hace poco.
