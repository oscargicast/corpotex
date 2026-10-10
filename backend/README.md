# backend

Django + DRF, Celery y el agente (ver `docs/adr/`). Se levanta con `docker compose up` desde la raíz del repo.

Comandos útiles (desde la raíz):

```sh
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_demo
docker compose exec web pytest
```

Estructura prevista (ADR 0008 y glosario): `config/` (settings, urls, celery), `core/`, `suppliers/`, `operations/`, `messaging/`, `manager/`, `agent/` (con `agent/persona/`), `seed/`.
