import type { ClockAnchor } from './model';

export type AssessmentClockSource = { wallNow(): number; monotonicNow(): number };
export const browserClock: AssessmentClockSource = {
  wallNow: () => Date.now(), monotonicNow: () => performance.now(),
};

/** Server time with a monotonic floor. Visibility never pauses an exam deadline. */
export class ServerClock {
  private anchor: ClockAnchor | null = null;
  private monotonicStart = 0;
  private monotonicBase = 0;
  private floor = 0;

  constructor(private readonly source: AssessmentClockSource) {}

  restore(anchor: ClockAnchor) {
    this.anchor = anchor;
    this.floor = Math.max(anchor.floor_ms, anchor.server_ms + Math.max(0, this.source.wallNow() - anchor.wall_ms));
    this.monotonicBase = this.floor;
    this.monotonicStart = this.source.monotonicNow();
  }

  observe(serverNow: string) {
    const server = Date.parse(serverNow);
    const next = this.anchor ? Math.max(server, this.now()) : server;
    this.restore({ server_ms: next, wall_ms: this.source.wallNow(), floor_ms: next });
  }

  now(): number {
    if (!this.anchor) return 0;
    this.floor = Math.max(this.floor,
      this.monotonicBase + Math.max(0, this.source.monotonicNow() - this.monotonicStart),
      this.anchor.server_ms + Math.max(0, this.source.wallNow() - this.anchor.wall_ms));
    return this.floor;
  }

  snapshot(): ClockAnchor {
    const now = this.now();
    return { server_ms: now, floor_ms: now, wall_ms: this.source.wallNow() };
  }

  remaining(deadline: string | null): number | null {
    return deadline === null ? null : Math.max(0, Math.ceil((Date.parse(deadline) - this.now()) / 1000));
  }
}
