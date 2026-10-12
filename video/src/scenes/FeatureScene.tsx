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
import { Recording } from "../components/Recording";
import { colors, fontFamily } from "../theme";

type FeatureSceneProps = {
  readonly number: number;
  readonly title: string;
  readonly role: string;
  // One line per caption; they take turns across the scene, in order.
  readonly captions: string;
  readonly recording: string;
  readonly recordingStartAt: number;
  readonly recordingPlaybackRate: number;
  readonly recordingHint: string;
  readonly style?: React.CSSProperties;
};

const FeatureSceneInner: React.FC<FeatureSceneProps> = ({
  number,
  title,
  role,
  captions,
  recording,
  recordingStartAt,
  recordingPlaybackRate,
  recordingHint,
  style,
}) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();

  const lines = captions.split("\n").filter((line) => line.trim() !== "");
  const headerFrames = 1.2 * fps;
  const captionFrames = Math.max(1, (durationInFrames - headerFrames) / Math.max(1, lines.length));
  const captionIndex = Math.min(
    lines.length - 1,
    Math.max(0, Math.floor((frame - headerFrames) / captionFrames)),
  );
  const captionStart = headerFrames + captionIndex * captionFrames;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.ink,
        fontFamily,
        color: colors.canvas,
        ...style,
      }}
    >
      {/* Header: number, title, role */}
      <div
        style={{
          position: "absolute",
          top: 44,
          left: 240,
          right: 240,
          height: 84,
          display: "flex",
          alignItems: "center",
          gap: 24,
          opacity: interpolate(frame, [0, 0.5 * fps], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
          translate: interpolate(frame, [0, 0.8 * fps], ["-40px 0px", "0px 0px"], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
        }}
      >
        <div
          style={{
            width: 72,
            height: 72,
            borderRadius: 20,
            backgroundColor: colors.brand,
            color: colors.ink,
            fontSize: 38,
            fontWeight: 800,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          {number}
        </div>
        <div style={{ fontSize: 46, fontWeight: 800, letterSpacing: -1, lineHeight: 1.1, flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {title}
        </div>
        <div
          style={{
            fontSize: 26,
            fontWeight: 600,
            color: colors.canvas,
            border: `2px solid ${colors.line}`,
            borderRadius: 999,
            padding: "8px 22px",
            whiteSpace: "nowrap",
          }}
        >
          {role}
        </div>
      </div>

      {/* Screen recording */}
      <div
        style={{
          position: "absolute",
          top: 150,
          left: 240,
          width: 1440,
          height: 810,
          borderRadius: 20,
          overflow: "hidden",
          border: `2px solid ${colors.line}`,
          boxShadow: "0 40px 120px rgba(0,0,0,0.5)",
          backgroundColor: colors.inkSoft,
          opacity: interpolate(frame, [0.3 * fps, 1 * fps], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
          scale: interpolate(frame, [0.3 * fps, 1.3 * fps], [0.96, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
            easing: Easing.bezier(0.16, 1, 0.3, 1),
            output: "perceptual-scale",
          }),
        }}
      >
        <Recording
          file={recording}
          startAt={recordingStartAt}
          playbackRate={recordingPlaybackRate}
          hint={recordingHint}
        />
      </div>

      {/* Caption that changes over time */}
      <div
        style={{
          position: "absolute",
          left: 240,
          right: 240,
          bottom: 24,
          height: 96,
          display: "flex",
          alignItems: "center",
          gap: 20,
        }}
      >
        <div
          style={{
            width: 8,
            height: 56,
            borderRadius: 4,
            backgroundColor: colors.brand,
            flexShrink: 0,
          }}
        />
        <div
          key={captionIndex}
          style={{
            fontSize: 40,
            fontWeight: 600,
            lineHeight: 1.2,
            opacity: interpolate(
              frame,
              [captionStart, captionStart + 0.4 * fps],
              [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
            ),
            translate: interpolate(
              frame,
              [captionStart, captionStart + 0.6 * fps],
              ["0px 16px", "0px 0px"],
              {
                extrapolateLeft: "clamp",
                extrapolateRight: "clamp",
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              },
            ),
          }}
        >
          {lines[captionIndex] ?? ""}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const featureSceneSchema = {
  number: { type: "number", default: 1, description: "Número", integer: true, min: 1, keyframable: false, hiddenFromList: false },
  title: { type: "text-content", default: "", description: "Título" },
  role: { type: "text-content", default: "Gerente", description: "Rol" },
  captions: { type: "text-content", default: "", description: "Subtítulos (uno por línea)" },
  recording: { type: "text-content", default: "", description: "Grabación (public/recordings/)" },
  recordingStartAt: {
    type: "number",
    default: 0,
    description: "Saltar segundos de la grabación",
    min: 0,
    step: 0.5,
    keyframable: false,
    hiddenFromList: false,
  },
  recordingPlaybackRate: {
    type: "number",
    default: 1,
    description: "Velocidad de la grabación",
    min: 0.5,
    max: 4,
    step: 0.25,
    keyframable: false,
    hiddenFromList: false,
  },
  recordingHint: { type: "text-content", default: "", description: "Qué grabar" },
} as const satisfies InteractivitySchema;

export const FeatureScene = Interactive.withSchema({
  Component: FeatureSceneInner,
  componentName: "<FeatureScene>",
  schema: featureSceneSchema,
  wrapInSequence: true,
});
