# 0019. Estilo por usuario y refresco diario automático

- Estado: aceptada (decisión de Oscar; diseño de `personalidad`). Ajusta el ADR 0011 en dónde se guarda el estilo.
- Fecha: 2026-10-10

## Contexto

Oscar quiere que el estilo aprenda solo, todos los días, y que el `BOSS.md` sea un dato del usuario en la BD. Ahora todos los usuarios tienen el asistente del dashboard (ADR 0017), y el Gerente además tiene el agente que escribe por él en WhatsApp.

## Decisión

- El estilo es un campo del usuario (`User`; `backend` define el nombre) en lugar de `Config.manager_style`. El agente de WhatsApp usa el estilo del usuario dueño del número; hoy, el Gerente.
- `User.style_md` (estilo vigente) y `User.style_refreshed_at`. `Config.agent_user` indica de quién es el número del agente; el seed pone al Gerente.
- Tabla `StyleVersion` {user, style_md, notes_snapshot, source: onboarding | daily | template | manual | rollback, changelog, created_at}. Guarda el historial. Volver atrás crea una versión nueva (`rollback`) que copia la anterior, así no se pierde nada.
- Tarea diaria `refresh_style` (Celery beat, ADR 0018), a las 03:00 de Lima, en hora real y no con el reloj simulado:
  - lee de nuestra BD, no de Evolution, los mensajes escritos a mano por el Gerente (`author=manager`) desde la última corrida, solo de conversaciones con números activos. Si no hay mensajes nuevos, no llama al modelo;
  - es incremental: estilo actual + mensajes nuevos anonimizados → estilo y notas por proveedor actualizados, más un changelog;
  - se aplica sola si pasa la validación: schema, secciones obligatorias, sin teléfonos ni RUC, largo razonable. Si no pasa, se queda el estilo actual y se crea una `Alert`;
  - el changelog ("hoy aprendí…") se muestra en el dashboard, solo como información.
- La reconstrucción completa sigue siendo el paso Estilo del onboarding (ADR 0011), que sí pasa por la revisión del Gerente.
- `no_phone` (proveedor sin números) y `not_allowed` (tiene números, pero ninguno activo) se mantienen separados, para que el Gerente sepa qué arreglar.

## Consecuencias

- Riesgo: un refresco malo cambia cómo el bot les escribe a todos los proveedores. Lo cubren la validación, el historial con vuelta atrás y el changelog visible.
- Consume la suscripción (ADR 0013) a las 03:00, fuera del horario de la demo.
