import type React from "react";
import {
  AbsoluteFill,
  Easing,
  Interactive,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  type InteractivitySchema,
} from "remotion";
import { colors, fontFamily } from "../theme";

type OutroProps = {
  readonly title: string;
  readonly url: string;
  readonly team: string;
  readonly style?: React.CSSProperties;
};

const OutroInner: React.FC<OutroProps> = ({ title, url, team, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.ink,
        justifyContent: "center",
        alignItems: "center",
        fontFamily,
        color: colors.canvas,
        textAlign: "center",
        padding: 120,
        ...style,
      }}
    >
      <div
        style={{
          fontSize: 92,
          fontWeight: 800,
          letterSpacing: -2,
          lineHeight: 1.1,
          maxWidth: 1500,
          opacity: interpolate(frame, [0, 0.7 * fps], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
          translate: interpolate(frame, [0, 1 * fps], ["0px 30px", "0px 0px"], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
        }}
      >
        {title}
      </div>
      <div
        style={{
          fontSize: 48,
          fontWeight: 600,
          color: colors.brand,
          marginTop: 40,
          opacity: interpolate(frame, [0.6 * fps, 1.2 * fps], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        {url}
      </div>
      <div
        style={{
          fontSize: 36,
          color: colors.muted,
          marginTop: 20,
          opacity: interpolate(frame, [1 * fps, 1.6 * fps], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        {team}
      </div>
    </AbsoluteFill>
  );
};

const outroSchema = {
  title: {
    type: "text-content",
    default: "Un agente que lleva la orden del cliente hasta que el proveedor entrega",
    description: "Título",
  },
  url: { type: "text-content", default: "corpotex.oscargicast.com", description: "URL" },
  team: {
    type: "text-content",
    default: "Oscar · Valeria · Nesky · Freddy",
    description: "Equipo",
  },
} as const satisfies InteractivitySchema;

export const Outro = Interactive.withSchema({
  Component: OutroInner,
  componentName: "<Outro>",
  schema: outroSchema,
  wrapInSequence: true,
});
