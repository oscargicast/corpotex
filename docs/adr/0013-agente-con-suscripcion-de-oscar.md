# 0013. El agente usa la suscripción de Claude de Oscar en la demo

- Estado: aceptada (decisión de Oscar). Reemplaza la parte de "API key" de 0004. La forma de conectar la cuenta cambió en el ADR 0022: desde el dashboard, sin `claude setup-token` ni token en `.env`.
- Fecha: 2026-10-10

## Contexto

El ADR 0004 decía que el agente se autenticaba con API key. Oscar prefiere usar su suscripción de Claude para el hackathon y no crear una API key.

## Decisión

- La cuenta se conecta desde el dashboard (ADR 0022) y la credencial queda en el `CLAUDE_CONFIG_DIR` propio del agente, que sigue sin la config personal de Oscar (ADR 0010).
- La extracción de estilo del onboarding (ADR 0011) también corre con Claude Code y no con la Messages API, porque esta solo acepta API key: el Agent SDK sin tools y con salida JSON validada en código.
- Para usar la API key, basta cambiar la variable de entorno; el código no cambia.

## Consecuencias

- Términos: la documentación del Agent SDK dice que, sin aprobación previa, un producto para terceros no puede funcionar con el login de claude.ai. Si esto se entrega a Corpotex, pasa a API key.
- Límites compartidos: las sesiones de desarrollo (`orquestador`, `backend`, `agente`, `disenador`, `personalidad`) usan la misma suscripción. Si llegan al límite de uso, el bot deja de responder. Durante la demo, esas sesiones deben estar quietas.
- El asistente del dashboard (ADR 0017) y el refresco diario del estilo (ADR 0019, a las 03:00 de Lima) también usan la suscripción.
- Privacidad: con la suscripción rigen los términos de consumidor. Si la cuenta de Oscar tiene activado el ajuste de privacidad que permite usar sus chats para mejorar los modelos, eso también cubre lo que mandan el bot y la extracción: los chats con proveedores (aunque vayan anonimizados) y las conversaciones del bot. Oscar lo revisa en claude.ai (Settings → Privacy) antes de la primera extracción.
- El helper común para lanzar el SDK aislado vive en `backend/agent/sdk.py` (`isolated_options()` para los turnos y `complete()` para la extracción). Es de `agente`; `personalidad` lo usa.
- El token no se imprime ni se pega en chats; solo vive en `.env` (gitignored).
