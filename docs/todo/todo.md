# TODO:

- El tab por pedir es innecesario http://localhost:3000/purchase-orders/pending ya que solo es un filtro de inventario. Solo añade el botón Pedir en todo cuando se agrega el filtro en inventario.
- En enlace de proveedores creo que es innecesario ahí, ya que tenemos un tab de proveedores.
- En http://localhost:3000/settings/claude mejora la connección con claude code.

- Mejora la vista de monitor.
- En http://localhost:3000/settings/claude quita el botón, simular orden de comercial.
- por qué debe haber una acción para desglosar de una orden sus pedidos? no podría ser algo que se muestre en real time con jev? Para tener el elemento wow del demo? Con la creación de la orden, se va haciendo allocate de pedidos line (PurchaseLine o similar) en una Purcha más grande quizás. El detalle es que una compra (pedido) que viene de 2 ordenes, sumaría al mismo purchaseline, no sé luego como diferenciar a cual corresponde cual, quizás no sea necesario, si va al mismo proveedor no hay problema, pero quizás se quiera mandar a distintos proveedores.
- agregar sonidos a las notificaciones del asistente.
- scraper de proveedores, de donde es la fuente? que le llegue una alerta al gerente por su asistente.
- El naming de Orden y Pedido se pueden reemplazar por Ventas y Compras.
- El área de producción necesita mover estados en los pedidos, cuando revisa ordenes, y mover ordenes también. Me confunde el estado sourcing y in_production, podemos simplificar esto? Puede pasar que un pedido está en sourcing y en in_production a la vez, o que si sea dependiende, dependiende del pedido, no sé como manejarlo. Además la idea es que producción marque lo menos posible y en su dashboard vea todo este rápido en monitor.