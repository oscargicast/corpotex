# Guion visual del pitch

Qué se proyecta en cada paso de la demo del domingo 11/10. Sigue el orden de D5 (`docs/planning.md`) y cabe en 8 minutos. Borrador de `disenador`; lo ajusta Oscar.

## Montaje (antes de las 09:00)

- Stack con el build de producción: `docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build`, y `docker compose exec web python manage.py seed_demo` (conserva el estilo aprobado; `--reset-style` lo recrea).
- Pantalla principal: Chrome con dos ventanas lado a lado de 960 px. Izquierda, el Gerente en `/`. Derecha, Comercial en `/`. Zoom al 100 %.
- Tercera ventana (o pestaña para cambiar con ⌘+Tab): `/simulator?present=1` como Gerente. Sirve también para mostrar a Producción si Oscar quiere enseñar el rol (login como `produccion`).
- Celular de Oscar: logueado como Gerente en `/orders`, con `https://corpotex.oscargicast.com/report/11111111-1111-4111-8111-000000000038` (el reporte de PT-0038, el pedido de la escena; el token es fijo en el seed) guardado como favorito.
- Abrir `/routes` una vez con wifi para que los tiles de Piura queden en caché; después no mover el zoom.
- Claude conectado (sin banner rojo en `/settings/claude`), instancia de WhatsApp `open` en `/onboarding/whatsapp`, tunnel arriba, laptop cargada, tethering probado.
- Valeria con su celular a mano, como "Confecciones del Norte".

## Guion (pantalla → qué se ve)

| # | Pantalla | Qué se ve | Quién |
|---|---|---|---|
| 1 | Gerente: `/` | Monitor: KPIs, la decisión pendiente, alertas y pagos por proveedor. Una frase: "esto es lo que hoy nadie ve hasta el día 9". | Oscar |
| 2 | Gerente: `/onboarding` → `/onboarding/style` | Los 4 pasos en verde y el estilo del Gerente con los ejemplos como burbujas. 20 segundos, no más. | Oscar |
| 3 | Comercial: `/orders` → "Simular orden de Comercial" → Caja Piura | La orden llega por la API y aparece desglosada contra inventario, con la ruta crítica. | Oscar |
| 4 | Gerente: `/orders/<nueva>` → "Confirmar desglose" (o Producción en la tercera ventana, si se quiere mostrar el rol) | Lo hace Producción; el Gerente también puede. La orden pasa a confirmada y el Monitor muestra la decisión de asignación. | Oscar |
| 5 | Gerente: `/` → tarjeta de decisión → "Cambiar proveedor" | El ranking del matching con barras por criterio (cumplimiento, precio, carga, calidad). Se aprueba. | Oscar |
| 6 | Gerente: `/purchase-orders/<pedido de Valeria>` | El agente le escribe a Valeria por WhatsApp real, con el estilo del Gerente. Ella responde desde su celular y el chat se ve en "Chat con el proveedor". | Oscar y Valeria |
| 7 | La misma vista, y el celular de Valeria | A la seña de Oscar, Valeria escribe que no puede terminar. El agente responde y escala. | Valeria |
| 8 | Gerente: `/` → tarjeta "Redistribución" → "Ver la ruta nueva" | Barra 400 hechas / 600 repartidas entre dos talleres, fecha y costo antes → después. En `/routes?before=&after=`, dos rutas de entrega a clientes que salen y vuelven de la planta: la del día original (gris) y la del día nuevo (verde punteada), con el aviso "La entrega a Caja Piura (CP-2026-0142) pasa del <día> al <día nuevo>". Las rutas son entregas a clientes; nada de recojos en talleres. | Oscar |
| 9 | Las dos ventanas a la vez | Avisos por rol: el Gerente recibe la decisión en el asistente y aprueba con el botón "Sí"; Comercial recibe solo "orden en peligro", sin precios ni proveedores. | Oscar |
| 10 | `/simulator?present=1` (atajo `P`) | El agente ya les escribió a los talleres nuevos: los contactos se resaltan y se les responde como taller. | Oscar o Nesky |
| 11 | Celular | `/report/<token fijo>`: 500 unidades con foto. Luego `/purchase-orders/PT-0038` muestra el avance y la foto en grande (lightbox). Cierre con "Marcar pagado" en los pagos. | Oscar |

## Mensajes de Valeria (paso 6 y 7)

Según `docs/guion-chat-de-rol.md`: mensajes cortos, sin guion palabra por palabra salvo la cancelación. Sugeridos:

1. Al recibir la propuesta del agente: "Ya, dale, me cuadra para esa fecha."
2. Avance con foto (una foto cualquiera de ropa o del taller): "Ya van 400 listos."
3. Cancelación, solo a la seña de Oscar, con la frase que dispara la redistribución: **"Jefe, no voy a poder terminar. Se me malogró la máquina."**

Nada de nombres reales, RUC ni cuentas.

## Plan B

- **Sin wifi:** el simulador y todas las vistas siguen; el mapa queda gris con marcadores y líneas. El tethering del celular reemplaza al wifi.
- **Si Valeria no puede o WhatsApp falla:** la cancelación se hace desde `/simulator?present=1` con el atajo del contacto "Confecciones del Norte" (el taller de PT-0038; con el seed actual es el `3`) y el mismo texto; la redistribución es la misma.
- **Si el agente tarda:** el modo presentación muestra "Escribiendo…"; si no responde en 30 segundos, se sigue con el paso 8 (la decisión ya está en el seed).
- **Si todo falla:** el video de respaldo de la corrida completa (D6, `CLAUDE.md`), guardado en la laptop y en el celular. Oscar lo graba a mano; como guía de los clics y tiempos está `docs/demo/respaldo/record.mjs` (Playwright headless sobre el stack real, `node record.mjs` y luego `./compose.sh ~/Desktop/corpotex-demo-respaldo.mp4`; gasta turnos del agente y muta la data, así que `seed_demo` después).
- No tocar `/settings/claude` ni "Desconectar" en vivo; no reseedear durante el pitch.

## Notas del ensayo (10/10, 20:40)

- Escena de WhatsApp real probada de punta a punta con Valeria: avance (10 s) y cancelación (11 s), ambas con el estilo extraído de Oscar.
- En la demo, Valeria reporta **400** polos ("ya van 400 del PT-0038") y no 720: así la cancelación deja 600 por repartir y la redistribución entra en dos o tres talleres (con 720 solo quedaron 280 y un taller).
- La respuesta del bot a la cancelación llega en dos burbujas (~10 s); esperar la segunda ("déjeme revisarlo y le confirmo") antes de pasar al Monitor.
- El Monitor tarda hasta 10 s más (tick) en mostrar la orden en peligro y los avisos por rol.
- Después del último deploy que toque prompts o tools y en el seed final: `seed_demo --reset-chats` (o `POST /api/assistant/reset/` por rol). Una sesión vieja del asistente arrastra reglas anteriores y puede negar una tool nueva (visto 10/10 21:30 con Producción).

