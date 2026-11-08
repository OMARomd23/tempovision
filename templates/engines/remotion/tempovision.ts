// Tempovision timing helpers for Remotion. Copied into src/tempovision/ by `tempovision timing --engine remotion`.
// Everything is a pure function of the frame, so renders are deterministic.
import { BEATS, DOWNBEATS, FPS, HITS, LYRICS, SECTIONS, type Hit, type Line, type Section, type Word } from "./timing";

/** Seconds at a frame. */
export const sec = (frame: number): number => frame / FPS;

/** Nearest frame for a time in seconds. */
export const frameAt = (seconds: number): number => Math.round(seconds * FPS);

/** The line being sung at this frame (or the last one that started, held until the next starts), or null. */
export function activeLine(frame: number, hold = 0.35): Line | null {
  const t = sec(frame);
  let current: Line | null = null;
  for (const line of LYRICS) {
    if (line.start <= t) current = line;
    else break;
  }
  if (!current) return null;
  const next = LYRICS[LYRICS.indexOf(current) + 1];
  const until = next ? Math.min(next.start, current.end + hold) : current.end + hold;
  return t < until ? current : null;
}

/** Lines visible in a window around the frame (for layouts that show several lines). */
export function linesBetween(fromSec: number, toSec: number): Line[] {
  return LYRICS.filter((l) => l.end >= fromSec && l.start < toSec);
}

/** 0 before the word, 0..1 while it is sung, 1 after. */
export function wordProgress(word: Word, frame: number): number {
  const t = sec(frame);
  if (t <= word.start) return 0;
  if (t >= word.end) return 1;
  return (t - word.start) / Math.max(1e-6, word.end - word.start);
}

/** True from the word's first sung frame (inclusive). */
export const wordStarted = (word: Word, frame: number): boolean => frame >= frameAt(word.start);

/** Index of the last beat at or before the frame (-1 before the first). */
export function beatIndex(frame: number, beats: number[] = BEATS): number {
  const t = sec(frame);
  let lo = 0;
  let hi = beats.length - 1;
  let ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (beats[mid] <= t + 1e-6) {
      ans = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return ans;
}

/** 1 on the beat, decaying exponentially to 0; `decay` is the half-life in seconds. Use for hits, not for everything. */
export function beatPulse(frame: number, opts: { decay?: number; beats?: number[] } = {}): number {
  const beats = opts.beats ?? BEATS;
  const i = beatIndex(frame, beats);
  if (i < 0) return 0;
  const dt = sec(frame) - beats[i];
  const half = opts.decay ?? 0.12;
  return Math.pow(0.5, dt / half);
}

/** 1-based bar number at the frame (0 before the first downbeat). */
export const barIndex = (frame: number): number => beatIndex(frame, DOWNBEATS) + 1;

/** The section at the frame. */
export function sectionAt(frame: number): Section | null {
  const t = sec(frame);
  return SECTIONS.find((s) => s.start <= t && t < s.end) ?? null;
}

/** Hits of the given kinds between two times (seconds). */
export function hitsBetween(fromSec: number, toSec: number, kinds?: string[]): Hit[] {
  return HITS.filter((h) => h.t >= fromSec && h.t < toSec && (!kinds || kinds.includes(h.kind)));
}

/**
 * Anticipation for a move that must land on a hit: 0 until `lead` seconds before the hit, 1 at the hit frame.
 * The hit itself should be instant; ease only the approach.
 */
export function approach(frame: number, hitSec: number, lead = 0.12): number {
  const t = sec(frame);
  if (t >= hitSec) return 1;
  if (t <= hitSec - lead) return 0;
  return (t - (hitSec - lead)) / lead;
}
