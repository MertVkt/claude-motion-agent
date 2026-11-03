import { Config } from "@remotion/cli/config";
// Audio-only (WAV) render: the CRF / pixel format in the main remotion.config.ts are invalid with WAV.
//   npx remotion render <composition> out.wav --codec=wav --config=remotion.audio.config.ts
// (deliver_png.sh copies this file into the job root if it is missing.)
Config.setOverwriteOutput(true);
Config.setConcurrency(null);
Config.setPublicDir("public");
