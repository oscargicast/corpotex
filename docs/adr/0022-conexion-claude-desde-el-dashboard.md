# 0022. Conectar la cuenta de Claude desde el dashboard

- Estado: aceptada (decisión de Oscar). Reemplaza en el ADR 0013 la parte de `claude setup-token` y el token en `.env`.
- Fecha: 2026-10-10

## Contexto

El ADR 0013 pedía que Oscar generara un token con `claude setup-token` y lo pegara en `.env`. Oscar quiere que la conexión viva en un apartado de configuración del Gerente, dentro del dashboard, y que esa única cuenta la usen todos los agentes del sistema (agente de WhatsApp, asistente de cada rol, extracción y refresco de estilo), para no pagar una API key por usuario. El flujo se copia del proyecto `mano` (`system/auth_providers/anthropic.py` y `frontend/www/scripts/connect-claude.js`), que ya lo tiene resuelto y probado.

## Decisión

Una sola cuenta de Claude por instalación, conectada por el Gerente desde `/settings/claude` (y como paso 0 del onboarding, antes de WhatsApp). La credencial se guarda en el servidor y la comparten todos los procesos que llaman al Agent SDK.

### Flujo, igual que en `mano`

1. **Start.** `POST /api/settings/claude/start/` (solo Gerente). El backend genera un `code_verifier` (PKCE) y devuelve la URL de autorización de claude.ai con `client_id` público de Claude Code, `redirect_uri` de la consola de Anthropic, `scope`, `code_challenge` (S256) y `state = verifier`. El verifier viaja como `state` y vuelve pegado al código, así el servidor no guarda nada entre pasos.
2. **El Gerente autoriza.** El dashboard abre esa URL en una pestaña nueva. Al terminar, la página de Anthropic le muestra un código largo con la forma `<code>#<state>`, que copia.
3. **Exchange.** `POST /api/settings/claude/exchange/ {code}`. El backend separa `code` y `state`, canjea en el endpoint de token de claude.ai con `grant_type=authorization_code` y `code_verifier=state`, consulta el perfil para obtener el tipo de suscripción, y escribe `.credentials.json` con `{claudeAiOauth: {accessToken, refreshToken, expiresAt, refreshTokenExpiresAt, scopes, subscriptionType, clientId}}`, atómico y con permisos 0600. Verifica que el archivo quedó bien antes de dar por conectado.
4. **Status.** `GET /api/settings/claude/status/` devuelve `{connected, method: oauth|api_key|none, subscription_type, expires_at, refresh_token_expires_at, expired, last_error}`. `expired` solo cuando venció el refresh token: el CLI renueva el access token solo en el siguiente arranque.
5. **Reconnect.** Mismo flujo con `is_reconnect=true`. Se dispara desde el banner que aparece cuando `status.expired` o cuando un turno falla con un error de autenticación (textos tipo "oauth token has expired", "authentication_error", "run /login", como clasifica `mano`), que el worker registra en `Config.claude_last_error`.
6. **Disconnect.** `POST /api/settings/claude/disconnect/` borra el archivo. Solo Gerente, con confirmación.
7. **API key como alternativa.** `POST /api/settings/claude/set-key/ {api_key}` guarda la key en un archivo aparte y un `apiKeyHelper` en `settings.json` del `CLAUDE_CONFIG_DIR`, excluyente con el OAuth: escribir una borra la otra, como en `mano`. Sirve para el día que se entregue a Corpotex (ADR 0013, términos).

### Dónde vive la credencial

- En el volumen `agent-home` del compose (`CLAUDE_CONFIG_DIR`, ADR 0018), en `.credentials.json`. Es el lugar donde el CLI de Claude Code la busca, así el Agent SDK la usa sin pasarle ningún token por `env=`. Ya no existe `CLAUDE_CODE_OAUTH_TOKEN` en `.env`.
- Django (`web`) y el `celery-worker` montan el mismo volumen: Django escribe, el worker lee. El worker la lee en cada spawn del CLI, así que un reconnect aplica al siguiente turno sin reiniciar nada.
- Nunca se guarda en la base de datos ni se devuelve por la API. `status` expone solo fechas y tipo de suscripción.

### UI (`disenador`)

- `/settings/claude`, solo Gerente, y el paso 0 del onboarding: estado (conectado como suscripción `max`/`pro`/… con fecha de vencimiento del refresh, o desconectado), botón **Conectar con Claude**, y debajo el flujo de 3 pasos de `mano`: "1. Inicia sesión en Claude, 2. Autoriza, 3. Pega el código", con un campo para pegar, botón "Pegar" desde el portapapeles y el error en línea si falta la parte después de `#`.
- Alternativa plegada: "Usar una API key".
- Banner global rojo en todas las vistas del Gerente cuando `expired` o `last_error`: "La conexión con Claude venció. Reconectar". Los demás roles ven "El asistente no está disponible; avisa al Gerente".
- En la demo: la cuenta queda conectada antes; el paso se muestra como hecho.

### Cambios en el modelo y en el agente

- `Config.claude_last_error` (texto, nullable) y `Config.claude_connected_at`.
- `agent/sdk.py` deja de inyectar `CLAUDE_CODE_OAUTH_TOKEN`; depende solo de `CLAUDE_CONFIG_DIR`.
- `run_turn` clasifica los errores de autenticación del CLI, los guarda en `Config.claude_last_error` y crea una `Alert` `claude_disconnected` para el Gerente (que llega por el asistente, ADR 0020, salvo que el propio asistente no pueda correr: entonces solo el banner y el Monitor).

## Consecuencias

- Ahorro: una sola suscripción para todos los usuarios y agentes. El límite de uso también es compartido (ADR 0013).
- Términos: sigue siendo la cuenta personal de Oscar bajo términos de consumidor (ADR 0013). Para entregar a Corpotex, el Gerente conecta una API key desde la misma pantalla.
- `CLIENT_ID`, `AUTHORIZE_URL`, `TOKEN_URL`, `REDIRECT_URI` y `SCOPES` se copian de `mano` a una constante única en `backend/core/claude_auth.py`; si Anthropic los rota, se cambian ahí.
- La extracción de estilo (`complete()`) y el refresco diario usan la misma credencial por el mismo volumen.
- `.env.example` pierde `CLAUDE_CODE_OAUTH_TOKEN`.
