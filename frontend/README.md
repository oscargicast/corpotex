# frontend

Dashboard en Next.js (ver `docs/adr/0003` y el glosario para las rutas). Se levanta con `docker compose up` desde la raíz del repo y queda en http://localhost:3000.

En desarrollo, `/api`, `/admin`, `/media`, `/static` y `/webhooks` se reescriben hacia `API_URL` (el servicio `web` de compose) sin quitar la barra final; en la demo pasan por el tunnel al mismo origen.

Comandos útiles (desde la raíz):

```sh
docker compose exec frontend pnpm add <paquete>
docker compose exec frontend pnpm typecheck
docker compose exec frontend pnpm build
```

## Mocks

Con `NEXT_PUBLIC_USE_MOCKS=1`, el navegador responde `auth`, `clock` y `me/badges` sin backend (`lib/mock-fetch.ts`). Usuarios: `gerente`, `comercial` y `produccion`, con la contraseña igual al usuario.

## Sesión por pestaña

El token vive en `sessionStorage`, así dos ventanas del mismo navegador pueden tener roles distintos (Gerente y Comercial lado a lado). `localStorage` solo abre pestañas nuevas con el último login. "Salir" cierra la sesión de esa pestaña sin revocar el token, para no sacar a las otras ventanas del mismo usuario.

## Worktree (ADR 0023)

Desde un worktree, solo el frontend, en `127.0.0.1:3001` y contra el backend de main, con un `docker-compose.override.yml` local (no versionado):

```sh
docker compose -p corpotex-fe up -d --build --no-deps frontend
```
