# 0032. Video de features con Remotion

- Fecha: 2026-10-11
- Estado: aceptada (pedido de Oscar, 11/10).

## Contexto

Además del video de respaldo del pitch (una corrida completa grabada a mano, `docs/demo/respaldo/`), Oscar quiere un video corto que muestre las mejores features una por una, con títulos, subtítulos y transiciones, para compartirlo después del hackathon. Las grabaciones de pantalla las hace a mano; lo que falta es el montaje repetible.

## Decisión

- Carpeta `video/` en la raíz del monorepo (ADR 0008), con su propio `package.json` (npm, Remotion 4). No toca `frontend/`.
- El video es código: `video/src/CorpotexFeatures.tsx` arma la línea de tiempo con `TransitionSeries`; cada feature es una escena `FeatureScene` con número, título, rol, subtítulos que cambian solos y la grabación de pantalla. Intro y cierre son escenas aparte. Cada escena está registrada también como composición propia para editarla sola en Remotion Studio.
- Las grabaciones viven en `video/public/recordings/` (gitignored, pesan mucho) con nombres fijos definidos en `docs/demo/video-features.md`. Mientras un archivo no existe, la escena muestra un marcador con el nombre que falta y qué grabar.
- 1920×1080, 30 fps, sin audio por ahora. Textos en español, código en inglés (ADR 0014).
- Previsualización con `npm run dev` (Remotion Studio); exportación con `npx remotion render CorpotexFeatures out/corpotex-features.mp4` o desde el botón "Render" del Studio.

## Consecuencias

- Cambiar una frase o un tiempo es editar un prop en el TSX (o en el Studio, que escribe de vuelta al código), sin reeditar nada en un editor de video.
- El render usa el Chrome headless que Remotion descarga solo; no hace falta ffmpeg.
- Las grabaciones no van al repo: el video final se regenera en la laptop de Oscar.
