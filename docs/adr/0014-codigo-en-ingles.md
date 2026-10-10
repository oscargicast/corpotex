# 0014. Código en inglés, documentación en español

- Estado: aceptada (decisión de Oscar)
- Fecha: 2026-10-10

## Contexto

Los docs de diseño nombraban apps, modelos, campos, estados, servicios y tools en español (`Proveedor`, `telefono_whatsapp`, `en_negociacion`, `encolar_turno`, `enviar_mensaje`).

## Decisión

- En inglés: todo el código. Eso incluye identificadores (apps, modelos, tablas, campos, valores de `choices`, funciones, clases, tools del agente, endpoints y claves JSON de la API), comentarios y docstrings.
- En español: la documentación (`docs/`, `CLAUDE.md`), los textos para personas (dashboard, admin, etiquetas como `verbose_name` y `status_display`, mensajes de WhatsApp y `BOSS.md`) y todo lo que lee el modelo: prompts, etiquetas XML y `RULES` del agente. Así el agente no se pasa al inglés al responder en español peruano. Las claves del JSON que devuelve el modelo van en inglés, porque las valida el código.

## Consecuencias

- `docs/glosario.md` lleva la tabla de equivalencias español → inglés (modelos, campos, servicios y tools) para que los docs y el código se lean juntos. Los ADR, el README de arquitectura y `CLAUDE.md` pasan a usar los nombres en inglés.
- El payload para resolver una decisión (`/api/manager/decisions/<id>/`) queda en inglés: `{action: approve | reject | change_supplier, supplier_id?, purchase_order_id?, note?}`.
