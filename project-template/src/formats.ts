/**
 * Standard delivery formats of the ad platforms.
 * Take sizes from here when you add a composition; never type them by hand.
 */
export const FORMATS = {
  /** TikTok, Reels, Shorts, Story: vertical full screen */
  vertical: { width: 1080, height: 1920 },
  /** Feed square */
  square: { width: 1080, height: 1080 },
  /** Feed vertical 4:5: the feed format that takes the most space on Meta */
  portrait: { width: 1080, height: 1350 },
  /** YouTube in-stream, landscape placements */
  landscape: { width: 1920, height: 1080 },
} as const;

export const FPS = 30;

/** Seconds to frames. sec(2.5) -> 75 */
export const sec = (s: number, fps: number = FPS) => Math.round(s * fps);

/** Safe area: margins that platform UI covers, keep text out of them (px, for 1080 width) */
export const SAFE_AREA = {
  vertical: { top: 210, bottom: 330, left: 60, right: 60 },
  square: { top: 60, bottom: 60, left: 60, right: 60 },
  portrait: { top: 80, bottom: 80, left: 60, right: 60 },
  landscape: { top: 60, bottom: 60, left: 100, right: 100 },
} as const;
