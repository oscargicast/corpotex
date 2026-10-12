import { Series, useVideoConfig } from "remotion";
import { Cut } from "./demo/Cut";
import { TitleCard } from "./demo/TitleCard";

// Two-minute demo for the pitch (docs/demo/video-features.md): a 2 s title card
// per feature, then only the moments where the feature shows, as hard cuts.
// Total: 3585 frames (119.5 s) at 30 fps.
export const Demo2min = () => {
  const { fps } = useVideoConfig();

  return (
    <Series>
      {/* 1. Puesta en marcha: Claude, WhatsApp y estilo · 8.0 s of cuts */}
      <Series.Sequence name="1 Título" durationInFrames={60} premountFor={fps}>
        <TitleCard number={1} title="Puesta en marcha: Claude, WhatsApp y estilo" />
      </Series.Sequence>
      <Series.Sequence name="1.1 onboarding @1.0s" durationInFrames={45} premountFor={fps}>
        <Cut file="01-onboarding.mp4" startAt={1.0} />
      </Series.Sequence>
      <Series.Sequence name="1.2 onboarding @4.5s" durationInFrames={45} premountFor={fps}>
        <Cut file="01-onboarding.mp4" startAt={4.5} />
      </Series.Sequence>
      <Series.Sequence name="1.3 onboarding @10.0s" durationInFrames={90} premountFor={fps}>
        <Cut file="01-onboarding.mp4" startAt={10.0} />
      </Series.Sequence>
      <Series.Sequence name="1.4 onboarding @21.0s" durationInFrames={60} premountFor={fps}>
        <Cut file="01-onboarding.mp4" startAt={21.0} />
      </Series.Sequence>
      {/* 2. Orden mágica: texto o foto, con insumos · 17.5 s of cuts */}
      <Series.Sequence name="2 Título" durationInFrames={60} premountFor={fps}>
        <TitleCard number={2} title="Orden mágica: texto o foto, con insumos" />
      </Series.Sequence>
      <Series.Sequence name="2.1 orden-magica @7.0s" durationInFrames={105} premountFor={fps}>
        <Cut file="02-orden-magica.mp4" startAt={7.0} />
      </Series.Sequence>
      <Series.Sequence name="2.2 orden-magica @11.5s" durationInFrames={60} premountFor={fps}>
        <Cut file="02-orden-magica.mp4" startAt={11.5} />
      </Series.Sequence>
      <Series.Sequence name="2.3 orden-magica @20.5s" durationInFrames={75} premountFor={fps}>
        <Cut file="02-orden-magica.mp4" startAt={20.5} />
      </Series.Sequence>
      <Series.Sequence name="2.4 orden-magica @36.5s" durationInFrames={60} premountFor={fps}>
        <Cut file="02-orden-magica.mp4" startAt={36.5} />
      </Series.Sequence>
      <Series.Sequence name="2.5 orden-magica @39.0s" durationInFrames={75} premountFor={fps}>
        <Cut file="02-orden-magica.mp4" startAt={39.0} />
      </Series.Sequence>
      <Series.Sequence name="2.6 orden-magica @43.0s" durationInFrames={90} premountFor={fps}>
        <Cut file="02-orden-magica.mp4" startAt={43.0} />
      </Series.Sequence>
      <Series.Sequence name="2.7 orden-magica @47.5s" durationInFrames={60} premountFor={fps}>
        <Cut file="02-orden-magica.mp4" startAt={47.5} />
      </Series.Sequence>
      {/* 3. Producción ajusta la ficha por prompt · 12.0 s of cuts */}
      <Series.Sequence name="3 Título" durationInFrames={60} premountFor={fps}>
        <TitleCard number={3} title="Producción ajusta la ficha por prompt" />
      </Series.Sequence>
      <Series.Sequence name="3.1 produccion-ajusta @0.5s" durationInFrames={30} premountFor={fps}>
        <Cut file="03-produccion-ajusta.mp4" startAt={0.5} />
      </Series.Sequence>
      <Series.Sequence name="3.2 produccion-ajusta @8.7s" durationInFrames={90} premountFor={fps}>
        <Cut file="03-produccion-ajusta.mp4" startAt={8.7} />
      </Series.Sequence>
      <Series.Sequence name="3.3 produccion-ajusta @17.5s" durationInFrames={75} premountFor={fps}>
        <Cut file="03-produccion-ajusta.mp4" startAt={17.5} />
      </Series.Sequence>
      <Series.Sequence name="3.4 produccion-ajusta @21.0s" durationInFrames={75} premountFor={fps}>
        <Cut file="03-produccion-ajusta.mp4" startAt={21.0} />
      </Series.Sequence>
      <Series.Sequence name="3.5 produccion-ajusta @28.0s" durationInFrames={90} premountFor={fps}>
        <Cut file="03-produccion-ajusta.mp4" startAt={28.0} />
      </Series.Sequence>
      {/* 4. Pedido en lote: el agente escribe solo · 11.2 s of cuts */}
      <Series.Sequence name="4 Título" durationInFrames={60} premountFor={fps}>
        <TitleCard number={4} title="Pedido en lote: el agente escribe solo" />
      </Series.Sequence>
      <Series.Sequence name="4.1 pedido-en-lote @6.0s" durationInFrames={60} premountFor={fps}>
        <Cut file="04-pedido-en-lote.mp4" startAt={6.0} />
      </Series.Sequence>
      <Series.Sequence name="4.2 pedido-en-lote @9.3s" durationInFrames={126} premountFor={fps}>
        <Cut file="04-pedido-en-lote.mp4" startAt={9.3} />
      </Series.Sequence>
      <Series.Sequence name="4.3 pedido-en-lote @26.0s" durationInFrames={150} premountFor={fps}>
        <Cut file="04-pedido-en-lote.mp4" startAt={26.0} />
      </Series.Sequence>
      {/* 5. Proveedores medidos, matching por histórico · 9.5 s of cuts */}
      <Series.Sequence name="5 Título" durationInFrames={60} premountFor={fps}>
        <TitleCard number={5} title="Proveedores medidos, matching por histórico" />
      </Series.Sequence>
      <Series.Sequence name="5.1 matching @1.0s" durationInFrames={120} premountFor={fps}>
        <Cut file="05-matching.mp4" startAt={1.0} />
      </Series.Sequence>
      <Series.Sequence name="5.2 matching @13.0s" durationInFrames={165} premountFor={fps}>
        <Cut file="05-matching.mp4" startAt={13.0} />
      </Series.Sequence>
      {/* 6. WhatsApp en vivo, dashboard al día · 15.8 s of cuts */}
      <Series.Sequence name="6 Título" durationInFrames={60} premountFor={fps}>
        <TitleCard number={6} title="WhatsApp en vivo, dashboard al día" />
      </Series.Sequence>
      <Series.Sequence name="6.1 whatsapp-en-vivo @6.0s" durationInFrames={144} premountFor={fps}>
        <Cut file="06-whatsapp-en-vivo.mp4" startAt={6.0} />
      </Series.Sequence>
      <Series.Sequence name="6.2 whatsapp-en-vivo @50.5s" durationInFrames={150} premountFor={fps}>
        <Cut file="06-whatsapp-en-vivo.mp4" startAt={50.5} />
      </Series.Sequence>
      <Series.Sequence name="6.3 whatsapp-en-vivo @60.5s" durationInFrames={90} premountFor={fps}>
        <Cut file="06-whatsapp-en-vivo.mp4" startAt={60.5} />
      </Series.Sequence>
      <Series.Sequence name="6.4 whatsapp-en-vivo @64.0s" durationInFrames={90} premountFor={fps}>
        <Cut file="06-whatsapp-en-vivo.mp4" startAt={64.0} />
      </Series.Sequence>
      {/* 7. Cancelación: avisos a todos, sin precios · 11.5 s of cuts */}
      <Series.Sequence name="7 Título" durationInFrames={60} premountFor={fps}>
        <TitleCard number={7} title="Cancelación: avisos a todos, sin precios" />
      </Series.Sequence>
      <Series.Sequence name="7.1 avisos-por-rol @8.0s" durationInFrames={75} premountFor={fps}>
        <Cut file="07-avisos-por-rol.mp4" startAt={8.0} />
      </Series.Sequence>
      <Series.Sequence name="7.2 avisos-por-rol @20.8s" durationInFrames={120} premountFor={fps}>
        <Cut file="07-avisos-por-rol.mp4" startAt={20.8} />
      </Series.Sequence>
      <Series.Sequence name="7.3 avisos-por-rol @44.5s" durationInFrames={75} premountFor={fps}>
        <Cut file="07-avisos-por-rol.mp4" startAt={44.5} />
      </Series.Sequence>
      <Series.Sequence name="7.4 avisos-por-rol @54.5s" durationInFrames={75} premountFor={fps}>
        <Cut file="07-avisos-por-rol.mp4" startAt={54.5} />
      </Series.Sequence>
      {/* 8. Rutas y flota en vivo · 18.0 s of cuts */}
      <Series.Sequence name="8 Título" durationInFrames={60} premountFor={fps}>
        <TitleCard number={8} title="Rutas y flota en vivo" />
      </Series.Sequence>
      <Series.Sequence name="8.1 rutas @4.0s" durationInFrames={105} premountFor={fps}>
        <Cut file="08-rutas.mp4" startAt={4.0} />
      </Series.Sequence>
      <Series.Sequence name="8.2 rutas @11.0s" durationInFrames={75} premountFor={fps}>
        <Cut file="08-rutas.mp4" startAt={11.0} />
      </Series.Sequence>
      <Series.Sequence name="8.3 rutas @16.0s" durationInFrames={105} premountFor={fps}>
        <Cut file="08-rutas.mp4" startAt={16.0} />
      </Series.Sequence>
      <Series.Sequence name="8.4 rutas @20.5s" durationInFrames={90} premountFor={fps}>
        <Cut file="08-rutas.mp4" startAt={20.5} />
      </Series.Sequence>
      <Series.Sequence name="8.5 rutas @40.5s" durationInFrames={165} premountFor={fps}>
        <Cut file="08-rutas.mp4" startAt={40.5} />
      </Series.Sequence>
    </Series>
  );
};
