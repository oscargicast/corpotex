# Presentación v2 (HTML puro, 11 slides)

Deck del pitch sin video: `index.html` es el cascarón con las slides 1 a 4 y 11; las slides 5 a 10 son fragmentos de disenador en `features/`, y los diagramas salen de Archify en `diagrams/`. Lienzo de 1600×900 escalado a la ventana; mismo look y navegación que el deck de Kenji (`../corpotex-reto7.html`).

## Navegación

- → / espacio / Enter / PageDown: siguiente. ← / PageUp / Backspace: anterior. Home / End. Clic en el tercio izquierdo retrocede, el resto avanza.
- `#n` en la URL abre la slide n. **R** reinicia la animación de la slide activa.
- Con `prefers-reduced-motion` cada slide muestra su estado final.

## Contrato de los fragmentos (slides 5 a 10)

Un archivo por feature en `features/NN-slug.html` (NN = 05 a 10, el orden del guion). Cada fragmento contiene, y nada más:

```html
<style>/* reglas con prefijo propio, p. ej. .f-orden-magica … */</style>
<section class="slide feature" data-feature="orden-magica">
  … markup en px dentro de un lienzo de 1600×900 (position:absolute funciona) …
  <div class="pg">05</div>
</section>
<script>
window.features = window.features || {};
window.features["orden-magica"] = {
  start() { /* arranca el replay; se llama al entrar a la slide y con la tecla R */ },
  reset() { /* vuelve al estado inicial; se llama al salir de la slide */ }
};
</script>
```

- El `data-feature` es el slug; el cascarón llama `start()` al entrar y `reset()` al salir.
- Con `prefers-reduced-motion`, `start()` debe dejar el estado final sin animar (`document.documentElement.classList.contains('reduced')` lo indica).
- Sin dependencias externas ni fetch: todo inline. Fuentes disponibles: `var(--serif)` (Zodiak), `var(--sans)` (Inter), `var(--mono)` (JetBrains Mono), con fallback local. Tokens: `--paper --cream --ink --sky --deep --stone --maroon --ok --warn`.
- Mobiliario disponible: `.eb` (eyebrow arriba a la izquierda), `.mark` (logo arriba a la derecha, copiar el `<svg class="mark">` de cualquier slide del cascarón), `.pg` (número abajo a la derecha).

## Integrar

```bash
node integrate.mjs        # inlinea features/*.html en index.html, entre <!-- features:start --> y <!-- features:end -->
```

Se puede repetir: cada corrida reemplaza el bloque completo. El resultado sigue siendo un solo `index.html` más `diagrams/`.

## Diagramas

`diagrams/flujo.workflow.json` → `node /Users/oscar/.claude-turbo/skills/archify/bin/archify.mjs finalize workflow docs/demo/pitch/v2/diagrams/flujo.workflow.json docs/demo/pitch/v2/diagrams/flujo.html --quality showcase --json` (desde la raíz del repo). La slide 4 lo embebe con `?theme=light&embed=1`; al entrar a la slide el iframe se recarga para que el trazo se dibuje de nuevo.
