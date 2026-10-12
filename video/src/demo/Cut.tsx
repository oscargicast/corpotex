import { Video } from "@remotion/media";
import type React from "react";
import { AbsoluteFill, Interactive, staticFile, useVideoConfig, type InteractivitySchema } from "remotion";
import { colors } from "../theme";

type CutProps = {
  // File name inside public/recordings/.
  readonly file: string;
  // Second of the recording where this cut starts.
  readonly startAt: number;
  readonly style?: React.CSSProperties;
};

// One cut of a screen recording, full frame, real speed. Length comes from the
// enclosing sequence; the waits of the real system are skipped by cutting.
const CutInner: React.FC<CutProps> = ({ file, startAt, style }) => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: colors.ink, ...style }}>
      <Video
        src={staticFile(`recordings/${file}`)}
        trimBefore={Math.round(startAt * fps)}
        premountFor={fps}
        muted
        objectFit="contain"
        style={{ width: "100%", height: "100%" }}
      />
    </AbsoluteFill>
  );
};

const cutSchema = {
  file: { type: "text-content", default: "", description: "Grabación" },
  startAt: { type: "number", default: 0, description: "Desde el segundo", min: 0, step: 0.5, keyframable: false, hiddenFromList: false },
} as const satisfies InteractivitySchema;

export const Cut = Interactive.withSchema({
  Component: CutInner,
  componentName: "<Cut>",
  schema: cutSchema,
  wrapInSequence: true,
});
