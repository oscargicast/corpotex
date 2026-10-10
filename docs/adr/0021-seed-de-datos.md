# 0021. Seed de datos inventados con un comando de Django

- Estado: aceptada (decisión de Oscar)
- Fecha: 2026-10-10

## Contexto

No hay datos reales de Corpotex (no llegaron los PDFs de Comercial). La demo necesita un catálogo, proveedores, órdenes en distintos estados y la escena del taller que cancela, con fotos de materiales y de prendas para que el dashboard se vea real.

## Decisión

- Un comando `python manage.py seed_demo` (idempotente: borra y recrea los datos de demo, nunca los usuarios ni la configuración de WhatsApp) carga todo desde fixtures en `backend/seed/`:
  - `data/*.json`: marcas, clientes, materiales, productos, proveedores con tarifas y notas, órdenes con ítems, pedidos, avances, pagos, alertas, decisiones y versiones de estilo.
  - `images/materials/*.jpg` y `images/products/*.jpg`: una foto por material y por producto, que el comando copia a `media/` y asocia a `Material.image` y `Product.image`.
- Los datos los genera Kenji con `infsh` a partir de nuestro modelo (`docs/backend/modelo-de-datos.md`) y de un brief con las reglas de coherencia. Las fotos salen de bancos libres de derechos (o se generan), nunca de fotos reales de Corpotex.
- Reglas de coherencia del seed:
  - 3 marcas (UNICRACK, NEXO, Línea Médica Corpotex), 4 clientes (Caja Piura, un colegio de Piura, AIDER, PIQA).
  - Materiales con SKU, tipo, unidad y stock; productos con su lista de materiales (`ProductMaterial.qty_per_unit`) para que el desglose cuadre.
  - Proveedores: 1 planta propia, 3 talleres de costura en Piura (uno es el proveedor real de la demo, "Confecciones del Norte"), 4 proveedores de insumos (3 de Lima, 1 de México que cobra en USD). Tarifas con precio histórico, notas de trato distintas y puntajes.
  - Órdenes en todos los estados, con fechas relativas al reloj simulado (`T+N días`) para que la demo funcione cualquier día.
  - La escena de la demo precargada: la orden de Caja Piura (1000 polos UNICRACK), el pedido del taller que va a cancelar con 400 unidades avanzadas, y dos talleres con capacidad para absorber las 600 restantes.
  - 3 `StyleVersion` con changelog y un `BOSS.md` base.
- Los números simulados de proveedores (ADR 0016) se crean en el seed. Los dos números reales de la demo van como constantes en el script de seed (decisión de Oscar), no en `.env`: el de la proveedora real (`51906746241`, activo) y el del Gerente (`51907898162`, el número desde el que escribe el agente). El repo es público y Oscar lo acepta.

## Consecuencias

- `backend` implementa el comando y el formato de los fixtures; Kenji entrega los JSON y las imágenes en ese formato.
- Las imágenes entran al repo (son libres de derechos y pesan poco); `media/` sigue gitignored.
- `seed_demo` se corre al levantar el compose y antes de cada ensayo.
