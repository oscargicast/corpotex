# 0003. Frontend en Next.js

- Estado: aceptada
- Fecha: 2026-10-10

## Contexto

El tablero tiene 4 vistas (órdenes, pedidos, monitor con alertas, proveedores y talleres), debe funcionar en móvil y escritorio. El mapa de Piura quedó fuera (ADR 0015).

## Decisión

Next.js con TypeScript, consumiendo la API del backend.

## Consecuencias

- Front y back avanzan en paralelo contra el contrato de la API.
- Son dos servicios en desarrollo; hay que resolver cómo el front se autentica contra el backend.

## Alternativa considerada

Templates server-side con HTMX: un solo servicio y sin auth entre front y back, pero el equipo eligió Next.js.
