import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { useVideoConfig } from "remotion";
import { FeatureScene } from "./scenes/FeatureScene";
import { Intro } from "./scenes/Intro";
import { Outro } from "./scenes/Outro";

// Scenes follow docs/demo/video-features.md. Durations match the recordings in
// public/recordings/ at their playback rate. Total = sum of durations - 9 transitions x 15 frames.
export const CorpotexFeatures = () => {
  const { fps } = useVideoConfig();

  return (
    <TransitionSeries>
      <TransitionSeries.Sequence name="Intro" durationInFrames={120} premountFor={fps}>
        <Intro
          title="Corpotex"
          subtitle="El agente que lleva la orden hasta que el proveedor entrega"
          tag="Reto 7 · Piura Innova 2026"
        />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />

      <TransitionSeries.Sequence name="1 Puesta en marcha" durationInFrames={720} premountFor={fps}>
        <FeatureScene
          number={1}
          title="Puesta en marcha: Claude, WhatsApp y estilo"
          role="Gerente"
          captions={`El Gerente conecta su cuenta de Claude una sola vez.
Vincula el WhatsApp de la empresa escaneando un QR.
El sistema aprende cómo escribe el Gerente a partir de sus chats.`}
          recording="01-onboarding.mp4"
          recordingStartAt={0}
          recordingPlaybackRate={1.25}
          recordingHint="/settings → Conectar Claude → /settings/whatsapp con el QR → /settings/style con el borrador del estilo y Aprobar."
        />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />

      <TransitionSeries.Sequence name="2 Orden mágica" durationInFrames={1065} premountFor={fps}>
        <FeatureScene
          number={2}
          title="Orden mágica: por texto o foto, con insumos sugeridos"
          role="Comercial"
          captions={`Comercial escribe la orden como la pide el cliente, o sube una foto.
Cada línea se reconoce sola: producto del catálogo o producto nuevo.
Los insumos salen de la receta: los que hay en stock y los que hay que crear.
La orden nace con ficha técnica y fecha estimada por ruta crítica.`}
          recording="02-orden-magica.mp4"
          recordingStartAt={0}
          recordingPlaybackRate={1.5}
          recordingHint="/orders/new: cliente Caja Piura, ítem 1 con foto del polo y cantidad, ítem 2 por texto, resumen a la derecha, Crear orden y el detalle."
        />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />

      <TransitionSeries.Sequence name="3 Producción ajusta" durationInFrames={875} premountFor={fps}>
        <FeatureScene
          number={3}
          title="Producción revisa, ajusta por prompt y aprueba"
          role="Producción"
          captions={`Producción ve primero lo que tiene que revisar.
Si algo no cuadra, lo corrige con una instrucción en lenguaje natural.
Al aprobar, los insumos entran a "por pedir".`}
          recording="03-produccion-ajusta.mp4"
          recordingStartAt={0}
          recordingPlaybackRate={1.25}
          recordingHint="/orders como Producción → la orden nueva → 'Ajustar la ficha técnica con una instrucción' → Proponer → Aplicar → Aprobar y abastecer."
        />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />

      <TransitionSeries.Sequence name="4 Pedido en lote" durationInFrames={940} premountFor={fps}>
        <FeatureScene
          number={4}
          title="Pedido en lote: el agente escribe a los proveedores"
          role="Producción → Gerente"
          captions={`Cada orden reserva stock y acumula lo que falta.
Producción pide todo en un lote cuando le conviene.
El agente escribe a cada proveedor con el precio de referencia, en el estilo del Gerente.
Nunca pide cotización: propone precio y fecha.`}
          recording="04-pedido-en-lote.mp4"
          recordingStartAt={0}
          recordingPlaybackRate={1.25}
          recordingHint="/inventory: stock, reservado, disponible, chip Por pedir → Pedir todo. Gerente: decisión en el Monitor → Aprobar → toast 'Enviando por WhatsApp' → primer mensaje en /purchase-orders/<id>."
        />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />

      <TransitionSeries.Sequence name="5 Matching" durationInFrames={804} premountFor={fps}>
        <FeatureScene
          number={5}
          title="Proveedores medidos y matching por histórico"
          role="Gerente"
          captions={`Cada entrega califica al proveedor: cumplimiento, calidad, precio y carga.
El sistema propone el mejor proveedor para cada pedido y explica por qué.
El Gerente aprueba con un clic, o cambia; el cambio alimenta el histórico.`}
          recording="05-matching.mp4"
          recordingStartAt={0}
          recordingPlaybackRate={1}
          recordingHint="/suppliers con las fichas de desempeño → Monitor → decisión de asignación → Cambiar proveedor: ranking con barras por criterio → Aprobar."
        />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />

      <TransitionSeries.Sequence name="6 WhatsApp en vivo" durationInFrames={1370} premountFor={fps}>
        <FeatureScene
          number={6}
          title="WhatsApp en vivo: el dashboard se actualiza solo"
          role="Gerente"
          captions={`El proveedor responde por WhatsApp; el agente entiende y actualiza el pedido.
Fecha comprometida, avance y fotos aparecen en el dashboard sin que nadie los copie.
Si es decisión de jefe (precio, términos), el agente no decide: escala al Gerente.`}
          recording="06-whatsapp-en-vivo.mp4"
          recordingStartAt={3}
          recordingPlaybackRate={1.5}
          recordingHint="Dos ventanas: /purchase-orders/<id> con el chat y la línea de tiempo, y /simulator?present=1 (o el celular). Acepta la fecha → Confirmado; reporta avance con foto → barra y foto en el pedido."
        />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />

      <TransitionSeries.Sequence name="7 Avisos por rol" durationInFrames={1500} premountFor={fps}>
        <FeatureScene
          number={7}
          title="Cancelación: avisos a todos, sin precios"
          role="Gerente + Comercial"
          captions={`Un taller cancela a mitad del pedido.
El sistema reparte lo que falta entre otros talleres y recalcula fecha, costo y ruta.
Comercial y Producción se enteran al instante; precios y contactos solo los ve el Gerente.`}
          recording="07-avisos-por-rol.mp4"
          recordingStartAt={2}
          recordingPlaybackRate={1.25}
          recordingHint="El taller escribe 'no voy a poder terminar'. Gerente: tarjeta Redistribución con fecha y costo antes → después. Comercial: aviso 'orden en peligro' sin precios ni proveedor."
        />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />

      <TransitionSeries.Sequence name="8 Rutas" durationInFrames={1275} premountFor={fps}>
        <FeatureScene
          number={8}
          title="Rutas y flota en vivo"
          role="Producción"
          captions={`Producción arma el día de entregas en un clic, por vehículo y capacidad.
Rutas multiparada por Piura, desde la planta.
Cada vehículo se ve en vivo y cada entrega se marca sola.`}
          recording="08-rutas.mp4"
          recordingStartAt={0}
          recordingPlaybackRate={1.25}
          recordingHint="/routes: Volver a planificar el día → Sin asignar → Pasar a mañana. En vivo: Iniciar ruta → Simular → pantalla completa → primera parada Entregada."
        />
      </TransitionSeries.Sequence>

      <TransitionSeries.Transition presentation={fade()} timing={linearTiming({ durationInFrames: 15 })} />

      <TransitionSeries.Sequence name="Cierre" durationInFrames={150} premountFor={fps}>
        <Outro
          title="Un agente que lleva la orden del cliente hasta que el proveedor entrega"
          url="corpotex.oscargicast.com"
          team="Oscar · Valeria · Nesky · Freddy"
        />
      </TransitionSeries.Sequence>
    </TransitionSeries>
  );
};
