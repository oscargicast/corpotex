# frontend

Dashboard en Next.js (ver `docs/adr/0003` y el glosario para las rutas). Se levanta con `docker compose up` desde la raíz del repo y queda en http://localhost:3000.

En desarrollo, `/api`, `/admin`, `/media` y `/webhooks` se reescriben hacia `API_URL` (el servicio `web` de compose); en la demo pasan por el tunnel al mismo origen.

Comandos útiles (desde la raíz):

```sh
docker compose exec frontend pnpm add <paquete>
docker compose exec frontend pnpm typecheck
```
