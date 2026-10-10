# Arquitectura de Corpotex (para revisar antes de implementar)

Estado: propuesta, 2026-10-10. Lo marcado **ADR** ya está decidido (`docs/adr/`); lo marcado **propuesto** es diseño nuevo de este documento y espera tu ok.

## Resumen

Un agente de WhatsApp lleva cada orden de cliente hasta que el proveedor entrega. Los proveedores escriben al número de Oscar; la instancia `corpotex` de Evolution manda cada mensaje a Django por el tunnel `corpotex.oscargicast.com`. Django lo encola en Postgres y una tarea de Celery corre el turno con Claude Agent SDK: lee el estado fresco, actualiza pedidos y responde por Evolution. Lo que es decisión de jefe aparece en el dashboard Next.js, en el Monitor y en el contador del menú, y el Gerente decide ahí. El equipo ve todo en el dashboard, y cada usuario tiene un asistente con tools según su rol (ADR 0017).

## Diagramas

Abrir los `.html` en el navegador (funcionan sin servidor).

| Diagrama | Archivo |
|---|---|
| Arquitectura completa | [diagramas/sistema/sistema.html](diagramas/sistema/sistema.html) |
| Flujo 1: mensaje de un proveedor y turno del agente | [diagramas/turno-proveedor/turno-proveedor.html](diagramas/turno-proveedor/turno-proveedor.html) |
| Flujo 2: escalamiento al Gerente en el dashboard | [diagramas/escalamiento-gerente/escalamiento-gerente.html](diagramas/escalamiento-gerente/escalamiento-gerente.html) |
| Flujo 3 (demo): un taller cancela a mitad del pedido | [diagramas/taller-cancela/taller-cancela.html](diagramas/taller-cancela/taller-cancela.html) |

Cada carpeta guarda `candidate.json` (la fuente del diagrama) y los recibos de validación de archify.

## Componentes y responsabilidades

| Componente | Dónde corre | Responsabilidad | Origen |
|---|---|---|---|
| Evolution `corpotex` | mac-mini, k3s | Recibe todo lo del número de Oscar y manda `MESSAGES_UPSERT` al webhook; envía con `sendText` | ADR 0001 |
| Evolution `personal-whatsapp` + n8n pepita | mac-mini, k3s | Flujo existente. No se toca | ADR 0001 |
| Cloudflare Tunnel | laptop → Cloudflare | `/api`, `/admin`, `/webhooks`, `/static`, `/media` → Django :8000; el resto → Next.js :3000 | ADR 0006 |
| Cloudflare Access | Cloudflare | Protege `evolution.oscargicast.com`; el backend entra con service token | ADR 0006 |
| Django + DRF | laptop | API del dashboard, admin (usuarios y roles), webhook, API del Gerente, motor de dominio | ADR 0002 |
| Worker del agente | laptop, tareas de Celery | Toma turnos de la cola, corre el Agent SDK con nuestras tools, reloj acelerado | ADR 0004 y 0018 |
| Postgres | laptop, Docker | Datos y cola de turnos | ADR 0005; cola en Postgres: **propuesto** |
| Next.js | laptop | Dashboard (4 vistas) y simulador de chat | ADR 0003 |
| Asistente del dashboard | laptop, tareas de Celery | Chat en el dashboard para cada usuario, con tools según su rol que llaman a los mismos servicios que la API | ADR 0017 |
| Redis + Celery (`celery-worker`, `celery-beat`) | laptop, Docker | Corre en segundo plano los turnos, el tick (~10 s), la extracción de estilo y el refresco diario `refresh_style` (03:00 Lima) | ADR 0018 y 0019 |
| Anthropic (Claude) | nube | Modelo detrás del Agent SDK, con la suscripción de Oscar | ADR 0004 y 0013 |

## Estructura del monorepo

Carpetas raíz: ADR 0008. Apps de Django: las de `docs/backend/modelo-de-datos.md`. Rutas del frontend: propuesta de la sesión `disenador`.

```
backend/                 Django + DRF (uv). Sesión: backend
  config/                settings, urls
  core/                  usuarios, Config (reloj), catálogo e inventario
  suppliers/             proveedores, tarifas
  operations/            órdenes, requerimientos, pedidos, avances, pagos
  messaging/             allowlist, conversaciones, mensajes, turnos, webhook, simulador
  manager/               decisiones, alertas, API del Gerente
  */services.py          servicios de dominio; las tools del agente llaman a estos, nunca a los modelos
  agent/                 tareas de Celery (turnos, tick) y tools del Agent SDK. Sesión: agente
  agent/persona/         estilo del Gerente y armado del prompt. Sesión: personalidad
frontend/                Next.js (pnpm). Sesión: disenador
  app/                   / (monitor), /login, /orders, /purchase-orders, /suppliers (solo Gerente), /simulator, /onboarding/..., /supplier-signup
infra/                   docker-compose.yml (Postgres, Redis, Celery worker y beat), cloudflared/config.yml
docs/                    adr/, arquitectura/, backend/, api/
```

## Modelo de dominio

La fuente de verdad es [`docs/backend/modelo-de-datos.md`](../backend/modelo-de-datos.md) (tablas, campos y estados en mermaid). La sesión `backend` lo está ajustando con: tabla `Turn` para la cola del worker, `Decision.purchase_orders` (M2M: una decisión aprueba un lote de pedidos), `Config.stage_durations`, `Supplier.is_in_house` y la calificación como campos `rating_*` de `PurchaseOrder`.

## Flujos

| # | Flujo | Diagrama |
|---|---|---|
| 0 | Alta de orden: Comercial registra (formulario o `POST /api/orders/`; el PDF es extra) → el motor desglosa contra inventario → Producción confirma → el motor propone proveedor con justificación → Decisión de asignación al Gerente → aprobada, el agente contacta | solo texto |
| 1 | Mensaje de un proveedor y turno del agente | [turno-proveedor](diagramas/turno-proveedor/turno-proveedor.html) |
| 2 | Escalamiento al Gerente en el dashboard | [escalamiento-gerente](diagramas/escalamiento-gerente/escalamiento-gerente.html) |
| 3 | Demo: un taller cancela, el sistema redistribuye y recalcula fecha y costo (sin rutas, ADR 0015) | [taller-cancela](diagramas/taller-cancela/taller-cancela.html) |
| 4 | Reloj acelerado: cada tick revisa plazos; sin avance → turno de seguimiento; fecha estimada pasa la comprometida → orden en peligro + alerta en el Monitor | solo texto |

## API

DRF con `TokenAuthentication` para el dashboard (ADR 0009). El dashboard llama por el mismo origen (tunnel en la demo, rewrites de Next.js en desarrollo). Todas las URLs llevan barra final. El contrato completo lo publica la sesión `backend` en `docs/api/` con drf-spectacular.

| Endpoint | Para | Origen |
|---|---|---|
| `POST /api/auth/login/` · `POST /api/auth/logout/` · `GET /api/auth/me/` | login (token de DRF) | propuesto |
| `GET, POST /api/orders/` · `GET /api/orders/<id>/` · `POST /api/orders/<id>/confirm/` | vista 1, Producción | propuesto |
| `GET /api/purchase-orders/` · `GET /api/purchase-orders/<id>/` | vista 2 | propuesto |
| `GET /api/monitor/` | vista 3 | propuesto |
| `GET /api/suppliers/` | vista 4; teléfono y precios solo para Gerente | propuesto |
| `GET /api/payments/` · `POST /api/payments/<id>/pay/` | pagos; marcar solo Gerente | propuesto |
| `POST /api/simulator/messages/` | simulador de chat | propuesto |
| `POST /webhooks/evolution/<secret>/` | Evolution | ADR 0006; secreto en la URL según `.env.example` |
| `GET /api/manager/pending/` | Monitor del dashboard | ADR 0017 |
| `POST /api/manager/decisions/<id>/` con `{action: approve \| reject \| change_supplier, supplier_id?, purchase_order_id?, note?, channel?}`; idempotente, devuelve el estado nuevo | Monitor del dashboard y tool `resolve_decision` del asistente | ADR 0017 |

## El agente

- Claude Agent SDK, restringido a nuestras tools: sin archivos ni bash (ADR 0004).
- Tools (ADR 0010): `send_message(text)`, `confirm_purchase_order`, `record_progress`, `report_cancellation`, `escalate_to_manager`, `read_history`, atadas a la conversación del turno.
- Un turno a la vez por conversación: tabla `Turn` en Postgres con bloqueo por fila (ADR 0010). La tarea de Celery solo dispara el turno; la exclusividad la da la tabla (ADR 0018).
- Una sesión por conversación; cada turno lee estado fresco de la BD (ADR 0004 y 0010).
- No decide precio, términos ni cambio de taller: crea una Decisión, que aparece en el Monitor del Gerente.
- Reloj acelerado con un tick de Celery beat cada ~10 s (ADR 0018), con factor configurable (**propuesto**: 1 día simulado = 1 minuto).

## Seguridad

- Allowlist de números del equipo: lo que no está en la lista se descarta sin guardar ni responder (**propuesto**).
- Webhook con secreto compartido en la URL (`.env.example`). Alternativa: el webhook de Evolution tiene un campo `headers` (se ve en la config de pepita), que permitiría mandarlo como header.
- API con token de DRF (ADR 0009); usuarios, roles y contraseñas en el admin de Django (ADR 0002).
- El equipo ve el nombre del proveedor, no su número; solo el Gerente ve teléfonos, precios y pagos.
- Evolution detrás de Cloudflare Access; el backend entra con service token (ADR 0006).
- Las tools del asistente se arman en el servidor según el rol, y pasan por los mismos permisos y filtros que la API (ADR 0017).
- Secretos solo en `.env` y `.secret` (gitignored).

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Valeria hace de proveedor y sus mensajes también llegan a pepita | Revisar si el flujo de pepita reacciona; si sí, que otra persona haga ese papel |
| El pod de Evolution se reinicia seguido | Tras cada reinicio, verificar que `corpotex` vuelva a `open` |
| Wifi del evento | Tethering desde el celular; simulador de chat; video de respaldo |
| La laptop se apaga | Todo corre ahí: cargador y un ensayo completo antes del pitch |

## Preguntas abiertas

1. Números de la allowlist.
2. Reparto del equipo.
3. PDFs de ejemplo de Comercial: ¿el demo parsea PDF o usa formulario?
4. Hora de entrega, formato del pitch y pesos de los criterios.
