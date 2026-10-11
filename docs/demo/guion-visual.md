# Guion visual del pitch

Qué se proyecta en cada paso de la demo del domingo 11/10. Sigue el orden de D5 (`docs/planning.md`) y cabe en 8 minutos. Borrador de `disenador`; lo ajusta Oscar.

## Montaje (antes de las 09:00)

- Stack con el build de producción: `docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build`, y `docker compose exec web python manage.py seed_demo` (conserva el estilo aprobado; `--reset-style` lo recrea).
- Pantalla principal: Chrome con dos ventanas lado a lado de 960 px. Izquierda, el Gerente en `/`. Derecha, Comercial en `/`. Zoom al 100 %.
- Tercera ventana (o pestaña para cambiar con ⌘+Tab): `/simulator?present=1` como Gerente. Sirve también para mostrar a Producción si Oscar quiere enseñar el rol (login como `produccion`).
- Celular de Oscar: logueado como Gerente en `/orders`, con `https://corpotex.oscargicast.com/report/11111111-1111-4111-8111-000000000038` (el reporte de PT-0038, el pedido de la escena; el token es fijo en el seed) guardado como favorito.
- Abrir `/routes` una vez con wifi para que los tiles de Piura queden en caché; después no mover el zoom.
- Claude conectado (sin banner rojo en `/settings/claude`), instancia de WhatsApp `open` en `/settings/whatsapp`, tunnel arriba, laptop cargada, tethering probado.
- Valeria con su celular a mano, como "Confecciones del Norte".
- Si va el paso 3b: CP-2026-0161 (Colegio Los Algarrobos) sin clasificar, con "Desglosar componentes" visible para Producción. Si alguien aplicó la clasificación, solo un `seed_demo` la devuelve.
- Si va el paso 9b: ninguna solicitud de avance abierta (el reseed de las 06:30 lo garantiza). Domingo: el seguimiento automático no escribe, así que no hay riesgo de mensajes a Valeria durante el pitch.
- Si va el paso 6b: el reseed de las 06:30 deja la ruta de hoy planificada para los 3 vehículos y sin iniciar. Antes del pitch, como Producción en `/routes`, revisar:
  - En Planificar, los 3 vehículos tienen que estar "Planificada": Furgón 1 al 97 %, Camioneta 2 al 98 % y Moto 3 al 80 %. CP-2026-0177 tiene que estar en "Sin asignar".
  - En En vivo, los 3 tienen que estar "Sin señal", con "Iniciar ruta" visible. La etiqueta del mapa abajo a la izquierda debe decir "En vivo" (el SSE funciona). Si dice "Actualiza cada 3 s", el stream cayó al respaldo por polling: sirve igual, pero el movimiento se ve a saltos.
  - El worker tiene que tener registrada la tarea del simulador: `docker compose logs celery-worker | grep simulate_tick`.
  - **Si en el ensayo se simuló, se reprogramó o se movió algo, hay que correr `seed_demo` antes del pitch.** Las órdenes del furgón quedan entregadas y la ruta completada, y una ruta en curso ya no se puede volver a planificar.

## Guion (pantalla → qué se ve)

| # | Pantalla | Qué se ve | Quién |
|---|---|---|---|
| 1 | Gerente: `/` | Monitor: KPIs, la decisión pendiente, alertas y pagos por proveedor. Una frase: "esto es lo que hoy nadie ve hasta el día 9". | Oscar |
| 2 | Gerente: `/settings` → Estilo (`/settings/style`) | Arriba "Puesta en marcha 4/4" en verde; en Estilo, el estilo del Gerente con los ejemplos como burbujas. 20 segundos, no más. | Oscar |
| 3 | Comercial: `/orders` → "Simular orden de Comercial" → Caja Piura | La orden llega por la API y aparece desglosada contra inventario, con la ruta crítica. | Oscar |
| 3b | **Opcional, lo decide Oscar en el ensayo.** Producción: `/orders/CP-2026-0161` → "Desglosar componentes" | Creación mágica: la IA reconoce el polo del catálogo con su receta y propone la casaca como producto nuevo con los insumos que faltan. No se aplica. Detalle abajo. | Oscar |
| 4 | Gerente: `/orders/<nueva>` → "Confirmar desglose" (o Producción en la tercera ventana, si se quiere mostrar el rol) | Lo hace Producción; el Gerente también puede. La orden pasa a confirmada y el Monitor muestra la decisión de asignación. | Oscar |
| 5 | Gerente: `/` → tarjeta de decisión → "Cambiar proveedor" | El ranking del matching con barras por criterio (cumplimiento, precio, carga, calidad). Se aprueba. | Oscar |
| 6 | Gerente: `/purchase-orders/<pedido de Valeria>` | El agente le escribe a Valeria por WhatsApp real, con el estilo del Gerente. Ella responde desde su celular y el chat se ve en "Chat con el proveedor". | Oscar y Valeria |
| 6b | **Opcional, la decide Oscar en el ensayo.** Producción: `/routes` → Planificar → En vivo | Flota en vivo: "Volver a planificar el día" reparte las órdenes listas entre los 3 vehículos según su capacidad, y la que no cabe queda en "Sin asignar" con su motivo. En En vivo, el Furgón 1 sale de la planta a pantalla completa y entrega su primera parada solo, a unos 23 s de pulsar Simular. Unos 1 min 30 s; detalle abajo. Valeria espera la seña para el paso 7. | Oscar |
| 7 | La misma vista, y el celular de Valeria | A la seña de Oscar, Valeria escribe que no puede terminar. El agente responde y escala. | Valeria |
| 8 | Gerente: `/` → tarjeta "Redistribución" → "Ver la ruta nueva" | Barra 400 hechas / 600 repartidas entre dos talleres, fecha y costo antes → después. En `/routes?before=&after=`, dos rutas de entrega a clientes que salen y vuelven de la planta: la del día original (gris) y la del día nuevo (verde punteada), con el aviso "La entrega a Caja Piura (CP-2026-0142) pasa del <día> al <día nuevo>". Las rutas son entregas a clientes; nada de recojos en talleres. | Oscar |
| 9 | Las dos ventanas a la vez | Avisos por rol: el Gerente recibe la decisión en el asistente y aprueba con el botón "Sí"; Comercial recibe solo "orden en peligro", sin precios ni proveedores. | Oscar |
| 9b | **Opcional, la decide Oscar en el ensayo.** Comercial: asistente → "pídele avance a los pedidos de la CP-2026-0158" → "sí"; `/simulator` | Seguimiento a pedido: Comercial pide avance sin ver el chat; el agente le escribe al taller en el simulador (sin decir quién preguntó); Oscar contesta como el taller; a Comercial le llega el resumen en su asistente. Detalle abajo. | Oscar |
| 10 | `/simulator?present=1` (atajo `P`) | El agente ya les escribió a los talleres nuevos: los contactos se resaltan y se les responde como taller. | Oscar o Nesky |
| 11 | Celular | `/report/<token fijo>`: 500 unidades con foto. Luego `/purchase-orders/PT-0038` muestra el avance y la foto en grande (lightbox). Cierre con "Marcar pagado" en los pagos. | Oscar |

## Creación mágica (paso 3b, opcional)

Lo decide Oscar en el ensayo. Va después de que Comercial registra la orden y antes de "Por pedir".

1. Como Producción, abrir `/orders/CP-2026-0161` (Colegio Los Algarrobos): dos prendas descritas en texto libre, "Producto nuevo, sin ficha todavía".
2. Pulsar "Desglosar componentes". La propuesta tarda unos 10 s: Jev (TypeSafe AI) elige del catálogo y del inventario, y Claude propone solo lo que es nuevo. Mientras carga, Oscar habla. Si Jev falla, sigue Claude sola y tarda unos 20 s.
3. Mostrar que el polo se reconoce como un producto del catálogo (Polo deportivo UNICRACK, UNI-POD-01) con su receta: tela, cuello rib, hilo, etiqueta.
4. Mostrar que la casaca es un producto nuevo, con los insumos que faltan en el inventario (taslán, polar, cierre separable), marcados como "Insumo nuevo". Los nombres y códigos que propone la IA cambian un poco entre corridas.
5. **No pulsar "Confirmar desglose" en el ensayo ni en la demo.** Si se aplica, la orden ya no sirve para la demo hasta el próximo `seed_demo`. Para salir, "Cancelar".

Frase de pitch sugerida: **"Fabrican a medida: la IA reconoce lo que ya saben hacer y propone lo que falta comprar."**

## Flota en vivo (paso 6b, opcional)

Lo decide Oscar en el ensayo. Va entre el WhatsApp con Valeria (paso 6) y su cancelación (paso 7): mientras el taller produce, se muestran las entregas del día. La tabla no tiene una fila "Por pedir", y después del paso 5 el agente ya le está escribiendo a Valeria, así que este es el primer hueco que no corta una escena en vivo. Se hace en la tercera ventana, logueada como `produccion`.

1. **Planificar.** Abrir `/routes`; la pestaña Planificar abre por defecto. Arriba dice "8 órdenes listas · 2,750 prendas · flota de 2,450": no entra todo.
2. Pulsar **"Volver a planificar el día"**. Dice "Volver" porque el seed ya dejó el día planificado, y el resultado es el mismo. Mostrar las tres columnas:
   - Furgón 1: 3 entregas, 1 450 prendas, 97 % de capacidad.
   - Camioneta 2: 3 entregas, 98 %. Incluye CP-2026-0170, marcada "Atrasada", que el plan pone primero.
   - Moto 3: 1 entrega, 80 %.
   - En el mapa, una ruta por color.
3. En **"Sin asignar"** queda CP-2026-0177 (Colegio San José Obrero, 400 prendas) con "No cabe: capacidad". Pulsar **"Pasar a mañana"**: sale de la lista y queda programada para mañana, todavía a tiempo frente a su promesa.
4. **En vivo.** Cambiar a la pestaña En vivo y pulsar **"Iniciar ruta"** del Furgón 1. Las horas de llegada se recalculan desde la hora real.
5. Pulsar **"Simular"**. La velocidad viene en x40. Aparecen las etiquetas "Simulando" y "En vivo", con el punto que late. El selector x12, x40, x60 cambia la velocidad en plena simulación, sin que el furgón retroceda.
6. Pulsar el botón de **pantalla completa** (arriba a la derecha del mapa). El panel queda como cajón flotante; en el cajón, **"Seguir"** del Furgón 1 hace que el mapa lo acompañe.
7. El furgón llega a su primera parada (Caja Piura, agencia Sánchez Cerro) a unos 6 s de pulsar Simular. Se queda ahí unos 15 s, que son los 10 min de descarga acelerados. Luego la parada pasa sola a **"Entregada"**, con check en el mapa, y el contador a "1/3 entregas". Medido con el seed: **23 s desde Simular** a x40. A x60 son unos 15 s; a x12, unos 75 s.
8. Esc para salir de pantalla completa. Volver a la ventana del Gerente para el paso 7.

Duración objetivo: **1 min 30 s** (30 s en Planificar y 1 min en En vivo).

Si el furgón no se mueve (el worker no tomó la tarea): pulsar "Detener simulación" y luego **"Marcar entregada"** en la próxima parada. El mapa y el contador cambian igual.

Frase de pitch sugerida: **"Hoy nadie sabe dónde está el furgón hasta que llama el cliente. Producción arma el día en un clic, según la capacidad de cada vehículo, y cada entrega se ve en vivo."**

## Seguimiento a pedido (paso 9b, opcional)

Lo decide Oscar en el ensayo. Va después de los avisos por rol (paso 9), porque usa las mismas dos ventanas. Usa **CP-2026-0158**, cuyo único pedido abierto (PI-0044, Avíos Gamarra) va por el simulador: con CP-2026-0142 el mensaje saldría al WhatsApp real de Valeria.

1. **Comercial**, en su asistente: "pídele avance a los pedidos de la CP-2026-0158". En unos 6 s responde con la vista previa: "Voy a pedirle avance a Avíos Gamarra sobre el pedido PI-0044 … ¿Lo envío? (sí/no)". Pulsar **Sí**. Tarjeta "Avance pedido a Avíos Gamarra (PI-0044)". Frase: "Comercial no ve el chat con el proveedor, pero puede pedir el dato".
2. **Gerente**, en `/simulator`: unos 10 s después aparece la pregunta del agente a Avíos Gamarra, en el estilo del Gerente y sin decir quién la pidió. Contestar como el taller: **"van 1500 de los 3430, el resto el jueves"**. El agente agradece y registra el avance.
3. **Comercial**: unos 17 s después llega el aviso "Avíos Gamarra respondió sobre el PI-0044: tiene listas 1500 de 3430 unidades; espera terminar el resto el jueves 15". Sin texto del chat.
4. Si sobra tiempo, Producción en `/purchase-orders/PI-0044`: la línea de tiempo muestra "Avance pedido por Comercial", "esperando respuesta" y la respuesta.

Duración objetivo: **1 min**. Medido en el ensayo de la madrugada: 43 s de punta a punta.

Si se repite dentro de las 2 h, el agente no vuelve a escribir: responde "ya se le preguntó a las HH:MM; te aviso cuando conteste". Para repetir la escena hace falta un `seed_demo --reset-chats`.

Frase de pitch sugerida: **"Cualquiera del equipo pregunta por un pedido y el agente consigue la respuesta, sin que nadie tenga que abrir WhatsApp."**

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

