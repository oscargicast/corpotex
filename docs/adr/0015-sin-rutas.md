# 0015. No se implementan rutas

- Estado: reemplazada por 0024 (las rutas vuelven)
- Fecha: 2026-10-10

## Contexto

El jurado pide rutas multiparada en un mapa de Piura, y la escena de la demo dice "recalcula fecha, costo y ruta". En la entrevista, en cambio, las rutas casi no aplican: los proveedores de Lima envían por Sullana Express y Corpotex recoge en la agencia de Piura.

## Decisión

No se implementan rutas: no hay modelos `Route` ni `RouteStop`, ni mapa, ni vista `/routes`, ni endpoint `/api/routes/`. Al redistribuir se recalculan solo la fecha y el costo.

## Consecuencias

- Se quitan del modelo `Route`, `RouteStop` y todo lo que dependía de ellos: `ruta_id` en el detalle de la `Decision`, la ruta del recorrido de la demo, y las coordenadas de `Supplier` y de la planta en `Config`.
- La tarjeta "Redistribución" del dashboard muestra el antes y el después de la fecha estimada y del costo.
- En el pitch se explica por qué no hay rutas: el recojo es en la agencia. Es un criterio del jurado que queda sin cubrir a propósito.
