# Video de features (Remotion)

Montaje del video de features de Corpotex (ADR 0032). Qué escena es cada feature y qué grabar: `docs/demo/video-features.md`.

## Previsualizar

```bash
cd video
npm install        # solo la primera vez
npm run dev        # abre Remotion Studio en el navegador
```

En el Studio, `CorpotexFeatures` es el video completo; en la carpeta "Escenas" están intro, una escena de feature y el cierre para editarlas solas. Lo que se cambia en el Studio se escribe de vuelta al código.

## Grabaciones

`node record.mjs` las graba solas con Playwright contra el stack (`BASE`, por defecto `http://127.0.0.1:3000`), una por escena, en `public/recordings/` (gitignored). `SCENES=02,03 node record.mjs` repite algunas. Muta datos de la demo: después, `seed_demo --reset-chats`. Detalle por escena en `docs/demo/video-features.md`.

Una grabación hecha a mano (QuickTime) se convierte así y se guarda con el nombre de su escena:

```bash
ffmpeg -i grabacion.mov -c:v libx264 -crf 18 -r 30 -an public/recordings/02-orden-magica.mp4
```

Si una grabación es más larga que la escena, en `src/CorpotexFeatures.tsx` se ajusta `recordingStartAt` (segundos que se saltan) o `recordingPlaybackRate` (1.5 = más rápido).

## Exportar a MP4

```bash
cd video
npx remotion render CorpotexFeatures out/corpotex-features.mp4   # completo, 4:49
npx remotion render Demo2min out/demo-2min.mp4                   # pitch, 1:59.5
```

`Demo2min` es la versión del pitch: tarjetas de 2 s y cortes limpios de las mismas grabaciones (`src/Demo2min.tsx`); se copia a `docs/demo/pitch/demo-2min.mp4` para la slide del deck.

Sale un H.264 de 1920×1080 a 30 fps en `out/` (gitignored). La primera vez descarga un Chrome headless (unos 150 MB). Para una versión más liviana para WhatsApp: `--crf 28 --scale 0.5`. También se puede exportar desde el botón "Render" del Studio, que muestra las mismas opciones.

Unos cuadros como PNG para revisar sin renderizar todo:

```bash
npx remotion render CorpotexFeatures out/frames --frames=70,400,2100 --image-format=png
```
