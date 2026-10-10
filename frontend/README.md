# frontend

Dashboard en Next.js (ver `docs/adr/0003` y el glosario para las rutas). Se levanta con `docker compose up` desde la raíz del repo y queda en http://localhost:3000.

En desarrollo, `/api`, `/admin`, `/media`, `/static` y `/webhooks` se reescriben hacia `API_URL` (el servicio `web` de compose) sin quitar la barra final; en la demo pasan por el tunnel al mismo origen.

Comandos útiles (desde la raíz):

```sh
docker compose exec frontend pnpm add <paquete>
docker compose exec frontend pnpm typecheck
docker compose exec frontend pnpm build
```

## Tipos de la API

`lib/api-types.ts` se genera desde `docs/api/openapi.json`; no se edita a mano. El contenedor solo monta `frontend/`, así que se corre con `docs/api` montado:

```sh
docker compose run --rm --no-deps -v "$PWD/docs/api:/docs-api:ro" frontend pnpm gen:types
```

`openapi-typescript` usa la API JS del compilador, que TypeScript 7 no trae: el script lo corre con `pnpm dlx` y su propio TypeScript 5.9.

## Carpetas nuevas

Turbopack dentro de Docker no ve las carpetas nuevas (rutas como `app/(dashboard)/orders/[id]/` o componentes como `components/assistant/`) hasta reiniciar: `docker compose restart frontend`. Los cambios en archivos que ya existen sí recargan solos.

## Mocks

Con `NEXT_PUBLIC_USE_MOCKS=1`, el navegador responde la API sin backend (`lib/mock-fetch.ts`, datos en `mocks/`): auth, clock, badges, monitor, decisiones, alertas, órdenes, pedidos y `settings/claude`. El estado vive en memoria de la pestaña y vuelve al inicio al recargar. Usuarios: `gerente`, `comercial` y `produccion`, con la contraseña igual al usuario.

## Sesión por pestaña

El token vive en `sessionStorage`, así dos ventanas del mismo navegador pueden tener roles distintos (Gerente y Comercial lado a lado). `localStorage` solo abre pestañas nuevas con el último login. "Salir" cierra la sesión de esa pestaña sin revocar el token, para no sacar a las otras ventanas del mismo usuario.

## Modo demo

`docker-compose.demo.yml` (en la raíz) sirve el build de producción: sin esperas de compilación ni overlay de errores en el proyector. El build corre al arrancar (un minuto):

```sh
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
docker compose logs -f frontend   # "Ready" cuando sirve
```

Desde un worktree hay que listar también el override local: `-f docker-compose.yml -f docker-compose.override.yml -f docker-compose.demo.yml`.

## Worktree (ADR 0023)

Desde un worktree, solo el frontend, en `127.0.0.1:3001` y contra el backend de main, con un `docker-compose.override.yml` local (no versionado):

```sh
docker compose -p corpotex-fe up -d --build --no-deps frontend
```
