import { Video } from "@remotion/media";
import { useEffect, useState } from "react";
import {
  AbsoluteFill,
  cancelRender,
  continueRender,
  delayRender,
  staticFile,
  useVideoConfig,
} from "remotion";
import { colors, fontFamily } from "../theme";

type RecordingProps = {
  // File name inside public/recordings/, e.g. "02-orden-magica.mp4".
  readonly file: string;
  // Seconds to skip at the start of the recording.
  readonly startAt: number;
  // 1 = real time; 1.5 speeds a long recording up.
  readonly playbackRate: number;
  // What to record, shown on the placeholder while the file is missing.
  readonly hint: string;
};

// Shows the screen recording when the file exists in public/recordings/;
// otherwise a placeholder that says which file is missing and what to record.
export const Recording: React.FC<RecordingProps> = ({
  file,
  startAt,
  playbackRate,
  hint,
}) => {
  const { fps } = useVideoConfig();
  const src = staticFile(`recordings/${file}`);
  const [exists, setExists] = useState<boolean | null>(null);
  const [handle] = useState(() =>
    delayRender(`Checking recordings/${file}`, { timeoutInMilliseconds: 20000 }),
  );

  useEffect(() => {
    let cancelled = false;
    fetch(src, { method: "HEAD" })
      .then((res) => {
        if (cancelled) return;
        setExists(res.ok);
        continueRender(handle);
      })
      .catch((err) => {
        if (cancelled) return;
        cancelRender(err);
      });
    return () => {
      cancelled = true;
    };
  }, [src, handle]);

  if (exists === null) {
    return null;
  }

  if (exists) {
    return (
      <Video
        src={src}
        premountFor={fps}
        trimBefore={Math.round(startAt * fps)}
        playbackRate={playbackRate}
        muted
        objectFit="cover"
        style={{ width: "100%", height: "100%" }}
      />
    );
  }

  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.inkSoft,
        backgroundImage:
          "repeating-linear-gradient(135deg, rgba(255,255,255,0.03) 0 24px, transparent 24px 48px)",
        justifyContent: "center",
        alignItems: "center",
        fontFamily,
        color: colors.muted,
        padding: 80,
        textAlign: "center",
      }}
    >
      <div style={{ fontSize: 28, fontWeight: 600, letterSpacing: 2, textTransform: "uppercase" }}>
        Falta la grabación
      </div>
      <div style={{ fontSize: 44, fontWeight: 800, color: colors.canvas, marginTop: 16 }}>
        video/public/recordings/{file}
      </div>
      <div style={{ fontSize: 30, lineHeight: 1.4, marginTop: 28, maxWidth: 1200 }}>{hint}</div>
    </AbsoluteFill>
  );
};
