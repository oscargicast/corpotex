# 0006. Backend en la laptop con Cloudflare Tunnel

- Estado: aceptada
- Fecha: 2026-10-10

## Contexto

Evolution API corre en el mac-mini y debe mandar el webhook a nuestro backend. Su URL pública (`evolution.oscargicast.com`) está detrás de Cloudflare Access, así que nuestras llamadas reciben 302 sin credenciales.

## Decisión

Backend y frontend corren en la laptop de Oscar, expuestos con el tunnel con nombre `corpotex` en el hostname genérico `corpotex.oscargicast.com`:

- `/api/`, `/admin/`, `/webhooks/`, `/static/` y `/media/` (fotos de avances y mensajes) van a Django (`localhost:8000`).
- Todo lo demás va a Next.js (`localhost:3000`).

Config en `infra/cloudflared/config.yml`. Para llamar a Evolution usamos un service token de Cloudflare Access.

## Consecuencias

- Sin pipeline de deploy, y el dashboard se puede abrir desde el celular (criterio móvil).
- Tunnel con nombre (no quick tunnel): la URL no cambia y queda fija en el webhook de la instancia `corpotex`.
- Hay que crear el service token y agregar a la app de Evolution en Access una policy Service Auth que lo incluya. El client id y el secret van en `.env`.
- La API y el admin quedan públicos: todo endpoint exige auth, y el webhook valida un secreto compartido con Evolution.
- El Gerente decide desde el dashboard, por el mismo tunnel. La API no necesita ser alcanzable por otra red (ADR 0017).
- Si la laptop se apaga o pierde internet, el bot se cae. Respaldo: tethering desde el celular y el simulador de chat.
