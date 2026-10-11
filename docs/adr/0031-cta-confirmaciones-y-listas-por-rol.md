# 0031. CTAs con un solo lenguaje, confirmación por modal, listas por rol y efecto de envío

- Fecha: 2026-10-11 (04:50)
- Estado: aceptada (pedido de Oscar, 11/10 04:45). Completa el ADR 0030 §4.

## Contexto

Después del PR #169 Oscar sigue viendo los CTA desiguales: "Aprobar y abastecer" sin icono, "Pedir avance" con un globo de chat en vez de WhatsApp, las píldoras de filtro del inventario distintas de los chips de proveedores, y acciones delicadas (aprobar, cancelar) que se ejecutan sin preguntar. Pide además que cada rol vea primero lo que le importa, filtros mínimos con búsqueda, un efecto visible cuando sale un mensaje por WhatsApp, sonido y cierre en los avisos del asistente, y un checkbox para marcar un número como de pruebas.

## Decisión

### 1. Botones

- Siempre icono y luego texto.
- Tres estilos, y nada más: **primario** (naranja de marca; uno por vista, la acción principal de esa vista), **secundario** (outline neutro) y **peligro** (outline rojo: Cancelar orden, Descartar proveedor). Misma altura, radio, peso y hover.
- Orden fijo en una barra de acciones: secundarios, peligro, primario a la derecha. En el detalle de la orden el primario es "Aprobar y abastecer" mientras hay ficha técnica por aprobar, y "Pedir avance a todos" (glifo de WhatsApp) en abastecimiento.
- Toda acción delicada confirma por modal (`ConfirmDialog` compartido, `<dialog>` nativo): título, una línea de consecuencia, Cancelar y el botón de confirmar con el mismo estilo e icono que el disparador. Aplica a Aprobar y abastecer, Cancelar orden, Pedir avance, Aprobar pedido, Pausar y Reanudar agente, Pedir todo y Descartar proveedor.

### 2. Filtros y listas por rol

- `FilterBar` compartido en Órdenes, Pedidos, Inventario y Proveedores: buscador (código, cliente, proveedor; en el cliente) y chips con contador. Sin selects de estado sueltos; las píldoras del inventario pasan a chips.
- **Comercial** mira la orden: Todas · Por confirmar (registrada o con ficha técnica; la píldora dice "Esperando a Producción") · Confirmadas · Avance pedido (la orden tiene un pedido esperando respuesta; `awaiting_reply` en la lista de órdenes).
- **Producción** mira lo que tiene que revisar: Por revisar (por defecto) · Confirmadas · Todas; en Pedidos, agrupación por proveedor con un toggle "Por proveedor" / "Lista" y chips Abiertos · Esperando respuesta · Entregados.
- **Gerente** ve todo con los mismos componentes.

### 3. Efecto de envío

Un toast compartido "Enviando por WhatsApp…" con el glifo, 1,2 s de animación y luego "Enviado a {proveedor}". Sale donde sale un mensaje de verdad: cuando el Gerente aprueba un pedido (primer contacto, ADR 0025) y en Pedir avance. "Pedir todo" de Producción no manda WhatsApp: los pedidos nacen `suggested` y el agente escribe cuando el Gerente aprueba; su estado de éxito dice "N pedidos generados · esperando aprobación del Gerente". Si Oscar quiere que Producción dispare el envío directo, es un cambio de regla (el Gerente deja de aprobar) y va en otro ADR.

### 4. Avisos del asistente, ruta crítica y simulador

- Sonido corto (Web Audio, sin archivo) al llegar un aviso nuevo con el chat abierto, con botón de silenciar guardado por navegador; cada aviso se puede cerrar en el chat sin reconocer la alerta, que sigue en el Monitor.
- La ruta crítica se abre y cierra desde su título; salen "Ver detalle" y "Comprimir".
- Al agregar un número a un proveedor, checkbox "Para pruebas (simulado)" (`simulated` en `POST /api/suppliers/<id>/numbers/`); el simulador muestra claro qué número simulado se usa y los mensajes que salen.

## Consecuencias

- Tareas: P6 y P8, P9 disenador; P7 rutas; P6b backend (`simulated` al crear números, `awaiting_reply` en la lista de órdenes). En `docs/planning.md`.
- Un modal más por acción delicada: en la demo, cada aprobación cuesta un clic extra; a cambio no se cancela una orden por error en vivo.
