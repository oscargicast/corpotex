# 0012. El agente no se hace pasar por humano

- Estado: aceptada (decisión de Oscar)
- Fecha: 2026-10-10

## Contexto

El agente escribe desde el número del Gerente y con su estilo. Un proveedor puede preguntar en serio si habla con una persona o con un bot, y el jurado puede preguntar qué pasa en ese caso.

## Decisión

Si el proveedor pregunta en serio, el agente no miente: dice que es el asistente del Gerente para los pedidos. Además escala al Gerente con `escalate_to_manager`, para que decida si sigue la conversación en persona.

## Consecuencias

- Va como regla en `agent/rules.py` y como escenario de prueba de `personalidad` en el simulador.
- El resto del tiempo el agente escribe con el estilo del Gerente sin anunciarse.
