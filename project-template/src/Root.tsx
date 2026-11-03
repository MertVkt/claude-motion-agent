import React from "react";
import { Composition } from "remotion";
import { SmokeTest } from "./compositions/SmokeTest";
import { FORMATS, FPS, sec } from "./formats";

/**
 * Registry of all compositions.
 * New ad: add a file under src/compositions/ and a <Composition> here.
 */
export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="SmokeTest-Vertical"
        component={SmokeTest}
        durationInFrames={sec(4)}
        fps={FPS}
        {...FORMATS.vertical}
        defaultProps={{ label: "9:16", safeKey: "vertical" as const }}
      />
      <Composition
        id="SmokeTest-Square"
        component={SmokeTest}
        durationInFrames={sec(4)}
        fps={FPS}
        {...FORMATS.square}
        defaultProps={{ label: "1:1", safeKey: "square" as const }}
      />
      <Composition
        id="SmokeTest-Portrait"
        component={SmokeTest}
        durationInFrames={sec(4)}
        fps={FPS}
        {...FORMATS.portrait}
        defaultProps={{ label: "4:5", safeKey: "portrait" as const }}
      />
      <Composition
        id="SmokeTest-Landscape"
        component={SmokeTest}
        durationInFrames={sec(4)}
        fps={FPS}
        {...FORMATS.landscape}
        defaultProps={{ label: "16:9", safeKey: "landscape" as const }}
      />
    </>
  );
};
