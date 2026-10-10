# 0016. Los celulares de proveedores viven solo en `AllowedNumber`

- Estado: aceptada (decisión de Oscar)
- Fecha: 2026-10-10

## Contexto

El celular de un proveedor estaba en dos lugares: `Supplier.whatsapp_phone` y `AllowedNumber.phone`. Había que mantenerlos sincronizados.

## Decisión

Se elimina `Supplier.whatsapp_phone`. Los celulares viven solo en `AllowedNumber` {phone, lid, name, role, supplier, active}, con FK al proveedor.

## Consecuencias

- Un proveedor puede tener 0, 1 o varios celulares (por ejemplo, el dueño y el encargado del taller).
- Dar de alta o importar un proveedor con celular crea su `AllowedNumber` con `active = false`. El Gerente lo activa a mano. Solo el Gerente ve los números.
- Un proveedor "tiene WhatsApp" si tiene al menos un `AllowedNumber` activo. Si no tiene ninguno, sus pedidos aprobados generan la `Alert` `no_channel`.
- La extracción de estilo (ADR 0011) lee solo los chats de números activos vinculados a un proveedor.
- `Conversation` apunta a `allowed_number` (FK, única por canal y número) en vez de guardar teléfono y proveedor. El proveedor sale de `allowed_number.supplier`, y el envío vuelve a chequear que ese número siga activo.
- `PurchaseOrder.conversation` fija a qué chat van los turnos que inicia el agente (primer mensaje y seguimientos), para que dos números del mismo proveedor no los dupliquen. El proveedor igual puede hablar del pedido desde cualquiera de sus números: `purchase_order_for_conversation` solo valida que el pedido sea de ese proveedor. La define `approve_purchase_orders`: la conversación con el mensaje entrante más reciente o, si no hay, la del primer número activo. Los seguimientos van a esa conversación; si su número se desactiva, el tick la vuelve a resolver.
- Los números no se borran: se desactivan.
- Números simulados: `AllowedNumber.simulated = true` con `phone = sim-<slug>`, que nunca coincide con un JID real. El webhook no los acepta y `send_text` no los manda por WhatsApp; sus conversaciones son del canal `simulator`. Cuentan como canal activo (no disparan `no_channel`) y la extracción de estilo los salta. Así los proveedores sin celular real operan por el simulador sin riesgo de un WhatsApp real.
