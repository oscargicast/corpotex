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

type IntroProps = {
  readonly title: string;
  readonly subtitle: string;
  readonly tag: string;
  readonly style?: React.CSSProperties;
};

const IntroInner: React.FC<IntroProps> = ({ title, subtitle, tag, style }) => {
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
        ...style,
      }}
    >
      <div
        style={{
          position: "absolute",
          width: 1400,
          height: 1400,
          borderRadius: 700,
          backgroundColor: colors.brand,
          opacity: 0.12,
          filter: "blur(120px)",
          scale: interpolate(frame, [0, 2 * fps], [0.6, 1.1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
            output: "perceptual-scale",
          }),
        }}
      />
      <div
        style={{
          fontSize: 36,
          fontWeight: 600,
          letterSpacing: 6,
          textTransform: "uppercase",
          color: colors.brand,
          opacity: interpolate(frame, [0, 0.5 * fps], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        {tag}
      </div>
      <div
        style={{
          fontSize: 160,
          fontWeight: 800,
          letterSpacing: -4,
          marginTop: 16,
          opacity: interpolate(frame, [0.2 * fps, 0.9 * fps], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
          translate: interpolate(frame, [0.2 * fps, 1.2 * fps], ["0px 40px", "0px 0px"], {
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
          fontSize: 54,
          fontWeight: 400,
          color: colors.muted,
          marginTop: 12,
          opacity: interpolate(frame, [0.8 * fps, 1.5 * fps], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        {subtitle}
      </div>
    </AbsoluteFill>
  );
};

const introSchema = {
  title: { type: "text-content", default: "Corpotex", description: "Título" },
  subtitle: {
    type: "text-content",
    default: "El agente que lleva la orden hasta que el proveedor entrega",
    description: "Subtítulo",
  },
  tag: { type: "text-content", default: "Reto 7 · Piura Innova 2026", description: "Etiqueta" },
} as const satisfies InteractivitySchema;

export const Intro = Interactive.withSchema({
  Component: IntroInner,
  componentName: "<Intro>",
  schema: introSchema,
  wrapInSequence: true,
});
