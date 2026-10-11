# 0030. Pausa del agente por proveedor y global, ficha del proveedor en la lista y capacidad de planta en el Monitor

- Fecha: 2026-10-11 (04:15)
- Estado: aceptada (pedido de Oscar, 11/10 04:00). Ajusta el ADR 0016 (canal por proveedor) y la vista de proveedores del ADR 0012.

## Contexto

Oscar revisa `/suppliers` antes del pitch y pide cuatro cosas: que la tarjeta muestre la ficha de desempeño y el número de pedidos, con un filtro por taller o proveedor; que la planta Corpotex salga de la lista de proveedores y aparezca en el Monitor como un KPI de capacidad de planta ("lo que no me queda claro es cómo se mide"); un CTA para pausar todos los bots o el bot de un proveedor; y que el detalle "x de x activos" / "sin canal" se reemplace por el botón de pausa en los que tienen WhatsApp y por el logo de WhatsApp en rojo en los que no, con un filtro para encontrarlos.

Hoy no hay forma de callar al agente sin apagar el worker. Para la demo, poder pausar al agente con el número real de Valeria es también una red de seguridad.

## Decisión

### 1. Pausa del agente

- `Supplier.agent_paused` y `Config.agent_paused` (booleanos, falso por defecto). La pausa global vale para todos; la del proveedor, solo para él.
- Con pausa, el agente no le escribe al proveedor por ningún canal (WhatsApp y simulador). Los mensajes entrantes se siguen guardando y se ven en la conversación. `enqueue_turn` crea el turno ya `skipped` con la nota "agente en pausa" y no despacha `run_turn`, así la línea de tiempo muestra lo que no se mandó. El tick de seguimiento no considera a los pausados ni los marca esperando respuesta.
- Los asistentes del dashboard nunca se pausan.
- Al reanudar no se reproduce nada automáticamente: el tick retoma los seguimientos. Si cabe, los pedidos aprobados durante la pausa sin ningún mensaje del agente reciben su primer contacto al reanudar.
- API (Gerente): `PATCH /api/suppliers/<id>/ {agent_paused}` y `GET/PATCH /api/settings/agent/` → `{paused, paused_suppliers}`.

### 2. Lista de proveedores

- La lista expone, además de lo que ya tenía, `agent_paused`, `whatsapp_ready` (no es planta y tiene al menos un número activo), `purchase_orders_count` (total histórico) y `last_delivered_on`.
- La tarjeta: ficha de desempeño (Cumplimiento, Calidad, Carga), "Pedidos: N abiertos · M en total" y la última entrega. Sale el `ChannelPill` ("x de x activos" / "Sin canal"). En su lugar: con WhatsApp listo, el glifo de WhatsApp en verde y el botón "Pausar" o "Reanudar" (pill ámbar "Agente en pausa"); sin WhatsApp, el glifo en rojo con el texto "Sin WhatsApp" al lado, nunca solo el color.
- Header: "Pausar agente" / "Reanudar agente" con confirmación, junto a "Nuevo proveedor".
- Filtros como chips con contador: Todos, Talleres, Insumos, Producto terminado, Sin WhatsApp, En pausa. Se filtra en el cliente: la lista es corta.
- La planta propia (`is_in_house`) sale de la lista.

### 3. Capacidad de planta en el Monitor

`GET /api/monitor/` suma `plant: {name, weekly_capacity, units_in_progress, load_pct, open_purchase_orders}` y `agent: {paused, paused_suppliers}`. La medida, que responde la duda de Oscar: **unidades en pedidos de taller abiertos asignados a la planta sobre su capacidad semanal** (`weekly_capacity`, en unidades por semana). Es la misma `supplier_load` que ya usa la tarjeta de cada taller; en el Monitor se muestra como barra, con rojo desde 85 %, y el texto "X u. en curso de Y u./semana · N pedidos de taller". Cuando la planta esté al tope, el matching reparte a talleres externos (ADR 0025), así que el KPI explica por qué aparecen pedidos a talleres.

### 4. Lo demás que pidió Oscar en la misma ronda

- CTAs unificados en Órdenes, Pedidos, Inventario y Proveedores: un primario por vista, mismo color, forma y tamaño, hover visible en todos (también en filas y tarjetas).
- Monitor y avisos con menos texto: una línea por alerta con el dato que importa y el CTA; el detalle al click.
- El asistente del dashboard responde primero, en una o dos líneas, sin listas de pasos y con una sola acción sugerida; tope orientativo de 60 palabras. Es un cambio de prompt, no de tools.

## Consecuencias

- La pausa deja turnos `skipped` en la conversación: son parte del historial, no un error.
- Un proveedor pausado con entrega hoy no recibe la pregunta de "siempre se considera escribir" del ADR 0027; el Gerente lo ve en la tarjeta.
- Tareas: P1 backend (modelo, compuerta, API, Monitor), P2 disenador (CTAs), P3 disenador (Monitor), P4 disenador (proveedores), P5 personalidad (asistente breve), en `docs/planning.md`.
