import { Composition, Folder } from "remotion";
import { CorpotexFeatures } from "./CorpotexFeatures";
import { Demo2min } from "./Demo2min";
import { Cut } from "./demo/Cut";
import { TitleCard } from "./demo/TitleCard";
import { FeatureScene } from "./scenes/FeatureScene";
import { Intro } from "./scenes/Intro";
import { Outro } from "./scenes/Outro";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* 120 + 720 + 1065 + 875 + 940 + 804 + 1370 + 1500 + 1275 + 150 - 9 x 15 = 8684 frames (4:49). */}
      <Composition
        id="CorpotexFeatures"
        component={CorpotexFeatures}
        durationInFrames={8684}
        fps={30}
        width={1920}
        height={1080}
      />
      {/* Pitch version: 8 title cards of 2 s plus hard cuts, 3585 frames (1:59.5). */}
      <Composition
        id="Demo2min"
        component={Demo2min}
        durationInFrames={3585}
        fps={30}
        width={1920}
        height={1080}
      />
      <Folder name="Demo2min-Elementos">
        <Composition
          id="TitleCard"
          component={TitleCard}
          durationInFrames={60}
          fps={30}
          width={1920}
          height={1080}
          defaultProps={{ number: 2, title: "Orden mágica: texto o foto, con insumos" }}
        />
        <Composition
          id="Cut"
          component={Cut}
          durationInFrames={90}
          fps={30}
          width={1920}
          height={1080}
          defaultProps={{ file: "02-orden-magica.mp4", startAt: 7 }}
        />
      </Folder>
      <Folder name="Escenas">
        <Composition
          id="Intro"
          component={Intro}
          durationInFrames={120}
          fps={30}
          width={1920}
          height={1080}
          defaultProps={{
            title: "Corpotex",
            subtitle: "El agente que lleva la orden hasta que el proveedor entrega",
            tag: "Reto 7 · Piura Innova 2026",
          }}
        />
        <Composition
          id="FeatureScene"
          component={FeatureScene}
          durationInFrames={600}
          fps={30}
          width={1920}
          height={1080}
          defaultProps={{
            number: 2,
            title: "Orden mágica: por texto o foto, con insumos sugeridos",
            role: "Comercial",
            captions:
              "Comercial escribe la orden como la pide el cliente, o sube una foto.\nCada línea se reconoce sola: producto del catálogo o producto nuevo.\nLa orden nace con ficha técnica y fecha estimada por ruta crítica.",
            recording: "02-orden-magica.mp4",
            recordingStartAt: 0,
            recordingPlaybackRate: 1,
            recordingHint:
              "/orders/new: cliente Caja Piura, ítem 1 con foto del polo, ítem 2 por texto, Crear orden.",
          }}
        />
        <Composition
          id="Outro"
          component={Outro}
          durationInFrames={150}
          fps={30}
          width={1920}
          height={1080}
          defaultProps={{
            title: "Un agente que lleva la orden del cliente hasta que el proveedor entrega",
            url: "corpotex.oscargicast.com",
            team: "Oscar · Valeria · Nesky · Freddy",
          }}
        />
      </Folder>
    </>
  );
};
