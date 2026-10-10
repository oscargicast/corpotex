# 0007. El Gerente atiende pendientes y alertas desde su Pana

- Estado: reemplazada por 0017 (asistente en el dashboard)
- Fecha: 2026-10-10

## Contexto

El agente escala al Gerente lo que no puede decidir solo (precio, términos, cambio de proveedor) y le avisa de retrasos y órdenes en peligro. El Gerente es el cuello de botella de la empresa: necesita enterarse sin abrir el dashboard.

## Decisión

El Gerente tiene un Pana (en la demo, Kenji) con el trick `com.oscar.corpotex`, que le permite:

- Preguntar qué tiene pendiente (decisiones por tomar, órdenes en peligro, alertas).
- Recibir notificaciones cuando el agente escala algo o una orden entra en peligro.
- Responder ahí mismo (aprobar, rechazar, cambiar proveedor), y que la decisión vuelva al backend.

## Mecanismo (acordado con Kenji, mensaje 59)

- Kenji arma e instala el trick en su servidor a partir de nuestra spec. Nosotros entregamos el contrato de la API: endpoints, payloads de ejemplo y estados.
- Consulta: el trick llama `GET /api/manager/pending/` por la tailnet (laptop y servidor de Kenji). Django debe escuchar en `0.0.0.0:8000`, no en `127.0.0.1`.
- Decisión: el trick llama `POST /api/manager/decisions/<id>/` con `{action: approve|reject|change_supplier, supplier_id?, purchase_order_id?, note?}`. Debe devolver el estado nuevo y ser idempotente (si llega dos veces, no duplica).
- Notificaciones: el backend hace `POST /incoming` al bridge de Kenji con `source: "corpotex"` y un texto con prefijo `[Corpotex]` más un JSON `{kind, id, summary}`. Kenji distingue por `source`.
- Credenciales: Kenji guarda el token del Gerente en el estado privado del trick, nunca en el repo. Para las notificaciones prefiere un token del bridge propio de Corpotex, no el personal de Oscar.

## Consecuencias

- El backend necesita endpoints para pendientes y decisiones del Gerente, además del dashboard.
- El dashboard sigue mostrando lo mismo; el Pana es otro canal hacia el Gerente, no el único.
- Pendiente: quién hace de Gerente en la demo. La cuenta Pana es la de Oscar, así que lo directo es que sea Oscar usando la app de Kenji.
- Si Kenji no está disponible en la demo, el Gerente usa el dashboard.
