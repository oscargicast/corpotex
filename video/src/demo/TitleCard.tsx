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

type TitleCardProps = {
  readonly number: number;
  readonly title: string;
  readonly style?: React.CSSProperties;
};

// Two-second feature title: number, one line, brand kit. Hard cut in and out.
const TitleCardInner: React.FC<TitleCardProps> = ({ number, title, style }) => {
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
          display: "flex",
          alignItems: "center",
          gap: 40,
          maxWidth: 1600,
          padding: "0 80px",
          opacity: interpolate(frame, [0, 0.3 * fps], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
          translate: interpolate(frame, [0, 0.5 * fps], ["0px 28px", "0px 0px"], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
        }}
      >
        <div
          style={{
            width: 120,
            height: 120,
            borderRadius: 32,
            backgroundColor: colors.brand,
            color: colors.ink,
            fontSize: 64,
            fontWeight: 800,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          {number}
        </div>
        <div>
          <div style={{ fontSize: 30, fontWeight: 600, letterSpacing: 5, textTransform: "uppercase", color: colors.brand }}>
            Corpotex · Reto 7
          </div>
          <div style={{ fontSize: 76, fontWeight: 800, letterSpacing: -2, lineHeight: 1.1, marginTop: 10 }}>{title}</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

const titleCardSchema = {
  number: { type: "number", default: 1, description: "Número", integer: true, min: 1, keyframable: false, hiddenFromList: false },
  title: { type: "text-content", default: "", description: "Título" },
} as const satisfies InteractivitySchema;

export const TitleCard = Interactive.withSchema({
  Component: TitleCardInner,
  componentName: "<TitleCard>",
  schema: titleCardSchema,
  wrapInSequence: true,
});
