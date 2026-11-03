import React from "react";
import {
  AbsoluteFill, useCurrentFrame, useVideoConfig,
  interpolate, spring, Easing,
} from "remotion";
import { SAFE_AREA } from "../formats";

type Props = { label: string; safeKey: keyof typeof SAFE_AREA };

/**
 * Setup check composition.
 * Shows that the render pipeline works end to end:
 * animation + spring + safe area + fps/size readout.
 * Add real ad compositions as separate files under src/compositions/.
 */
export const SmokeTest: React.FC<Props> = ({ label, safeKey }) => {
  const frame = useCurrentFrame();
  const { width, height, fps, durationInFrames } = useVideoConfig();
  const safe = SAFE_AREA[safeKey];

  const pop = spring({ frame, fps, config: { damping: 14, mass: 0.7 } });
  const fade = interpolate(frame, [0, 15], [0, 1], {
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const sweep = interpolate(frame, [0, durationInFrames], [0, 1]);

  return (
    <AbsoluteFill style={{ backgroundColor: "#0B0D10", fontFamily: "Helvetica, Arial, sans-serif" }}>
      {/* animated background gradient */}
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at ${30 + sweep * 40}% ${40 + sweep * 20}%, #1E3A5F 0%, #0B0D10 60%)`,
        }}
      />

      {/* safe area frame: platform UI covers everything outside it */}
      <AbsoluteFill
        style={{
          top: safe.top, bottom: safe.bottom, left: safe.left, right: safe.right,
          border: "3px dashed rgba(255,255,255,0.22)",
          borderRadius: 18,
        }}
      />

      <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", opacity: fade }}>
        <div style={{ transform: `scale(${pop})`, textAlign: "center" }}>
          <div style={{ fontSize: 34, letterSpacing: 7, color: "#5EC8FA", fontWeight: 700 }}>
            SETUP OK
          </div>
          <div style={{ fontSize: 92, color: "#fff", fontWeight: 800, marginTop: 14 }}>
            {label}
          </div>
          <div style={{ fontSize: 40, color: "rgba(255,255,255,0.65)", marginTop: 18 }}>
            {width}×{height} · {fps} fps
          </div>
        </div>
      </AbsoluteFill>

      {/* frame counter, to check sync / dropped frames */}
      <div
        style={{
          position: "absolute", bottom: safe.bottom + 20, width: "100%",
          textAlign: "center", fontSize: 28, color: "rgba(255,255,255,0.45)",
        }}
      >
        frame {frame} / {durationInFrames}
      </div>
    </AbsoluteFill>
  );
};
