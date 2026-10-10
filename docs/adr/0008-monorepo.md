# 0008. Monorepo

- Estado: aceptada
- Fecha: 2026-10-10

## Contexto

Backend Django, frontend Next.js, infraestructura local (Postgres, tunnel) y documentación de diseño. Cuatro personas trabajando en paralelo durante día y medio.

## Decisión

Un solo repo con esta estructura:

```
backend/    Django + DRF, worker del agente y adaptadores de canal (uv)
frontend/   Next.js: tablero y simulador de chat (pnpm)
infra/      docker compose (Postgres, Redis, Celery worker y beat) y config del tunnel de Cloudflare
docs/       adr/, arquitectura/, api/
.env        en la raíz, compartido por backend e infra (gitignored)
```

## Consecuencias

- Un cambio que toca API y tablero va en un solo commit.
- El contrato de la API vive en `docs/api/` y lo lee el frontend.
- Cada carpeta tiene su propio gestor de dependencias; los comandos de desarrollo se documentan en la raíz.
