import { Config } from "@remotion/cli/config";

// --- Defaults for ad production ---
Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(95);
Config.setOverwriteOutput(true);

// H.264 at high quality: accepted by Meta, TikTok and Google Ads
Config.setCodec("h264");
Config.setCrf(18);            // 18 = visually close to lossless
Config.setPixelFormat("yuv420p");

// Parallel render
Config.setConcurrency(null);  // null = Remotion picks automatically

// In Studio, public/ is the asset root
Config.setPublicDir("public");
