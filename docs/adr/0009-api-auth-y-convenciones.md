# 0009. API: auth con token y convenciones

- Estado: aceptada
- Fecha: 2026-10-10

## Contexto

La API la usa el dashboard Next.js. `disenador` propuso sesión de Django; `backend` y el diseño de arquitectura, token.

## Decisión

- Auth: `TokenAuthentication` de DRF para el dashboard. Un solo mecanismo y sin CSRF.
- Todas las URLs llevan barra final (convención de Django), incluidas las del Gerente: `/api/manager/pending/` y `/api/manager/decisions/<id>/`. Las usan el Monitor del dashboard y la tool `resolve_decision` del asistente (ADR 0017).
- El contrato vive en `docs/api/`, generado con drf-spectacular (`/api/schema/`) más JSON de ejemplo. El frontend genera sus tipos TypeScript desde ahí.
- Los estados viajan con su texto en español (`status_display`).
- Sin websockets: el dashboard y el simulador consultan cada 3 s.

## Consecuencias

- El dashboard guarda el token y lo manda en cada request; en la demo va por el mismo origen (tunnel), en desarrollo por rewrites de Next.js.
