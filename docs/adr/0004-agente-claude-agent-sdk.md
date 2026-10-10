# 0004. Agente con Claude Agent SDK

- Estado: aceptada
- Fecha: 2026-10-10

## Contexto

El agente conversa con los proveedores por WhatsApp: un turno por cada mensaje entrante, con herramientas propias (leer historial, enviar por Evolution, actualizar pedido y orden, leer proveedor, escalar al Gerente). Opciones evaluadas: Claude Agent SDK (propuesta de Kenji) o el SDK de Anthropic con tool runner.

## Decisión

Claude Agent SDK en Python. La autenticación la define el ADR 0013 (suscripción de Oscar para la demo).

## Consecuencias

- Es el harness de Claude Code como librería: trae tools de archivos y bash. Hay que restringirlo a nuestras tools para que no toque el disco ni corra comandos.
- Una sesión por chat o pedido, reanudada en cada turno. Cada turno lee estado fresco de la BD; la sesión solo guarda el hilo.
- Verificar en la doc (code.claude.com/docs/en/agent-sdk) antes de implementar: cómo se registran tools propias, cómo se restringen las built-in, dónde guarda las sesiones y qué necesita instalado.

## Alternativa descartada

SDK de Anthropic con tool runner: más liviano y con el historial en nuestra BD, pero el equipo eligió Agent SDK.
