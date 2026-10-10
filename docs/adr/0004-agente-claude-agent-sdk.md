# 0004. Agente con Claude Agent SDK

- Estado: aceptada
- Fecha: 2026-10-10

## Contexto

El agente conversa con los proveedores por WhatsApp: un turno por cada mensaje entrante, con herramientas propias (leer historial, enviar por Evolution, actualizar pedido y orden, leer proveedor, escalar al Gerente). Opciones evaluadas: Claude Agent SDK (propuesta de Kenji) o el SDK de Anthropic con tool runner.

## Decisión

Claude Agent SDK en Python. Es Claude Code como librería: lanza el binario de Claude Code como subproceso y le habla por pipes con stream-json, el mismo mecanismo que `mano` implementó a mano en `system/session_manager.py`, pero ya resuelto (loop, sesiones, parseo de eventos) y con las tools como funciones Python. La cuenta se conecta una sola vez, desde el dashboard y solo por el Gerente (ADR 0022); el SDK la lee del `CLAUDE_CONFIG_DIR` compartido.

## Consecuencias

- Es el harness de Claude Code como librería: trae tools de archivos y bash. Hay que restringirlo a nuestras tools para que no toque el disco ni corra comandos.
- Una sesión por chat o pedido, reanudada en cada turno. Cada turno lee estado fresco de la BD; la sesión solo guarda el hilo.
- Verificar en la doc (code.claude.com/docs/en/agent-sdk) antes de implementar: cómo se registran tools propias, cómo se restringen las built-in, dónde guarda las sesiones y qué necesita instalado.

## Alternativa descartada

SDK de Anthropic con tool runner: más liviano y con el historial en nuestra BD, pero el equipo eligió Agent SDK.
