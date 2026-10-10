# 0002. Backend en Django con Django REST Framework

- Estado: aceptada
- Fecha: 2026-10-10

## Contexto

Hay día y medio y cuatro personas. El backend es mayormente CRUD (órdenes, pedidos, proveedores y talleres, pagos, alertas) con permisos por rol (Gerente, Comercial, Producción) y data de demo. Además recibe el webhook de WhatsApp, corre los turnos del agente y un reloj acelerado para seguimientos.

## Decisión

Django con Django REST Framework (DRF) para la API. Elegido por simplicidad.

## Por qué no FastAPI

- Lo que FastAPI hace mejor es async nativo. Aquí pesa poco: un turno del agente puede tardar decenas de segundos, así que corre fuera del request del webhook con cualquier framework. El ORM de Django tiene métodos async (`aget`, `asave`) para las tools del agente (ADR 0004).
- Django trae resuelto lo que más tiempo consume en este reto: ORM con migraciones, usuarios y grupos para los roles, y el admin para cargar data y como respaldo en la demo.

## Consecuencias

- El webhook guarda el mensaje entrante y responde 200 de inmediato; otro proceso corre el turno del agente.
- Roles como grupos de Django; un usuario sembrado por rol. Usuarios, roles y contraseñas se gestionan desde el admin de Django, no en Next.js.

## Alternativas descartadas

- FastAPI con clean architecture: se eligió un momento y se descartó por simplicidad. Sin admin, auth ni migraciones de serie, y más código por funcionalidad.
- django-ninja: API estilo FastAPI con OpenAPI automático; el equipo prefirió DRF.
