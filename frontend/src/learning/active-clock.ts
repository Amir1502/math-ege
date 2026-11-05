/** A monotonic clock whose elapsed time advances only while the task is visible. */
export class ActiveClock {
  private startedAt: number | null = null;
  private elapsedMs: number;

  constructor(initialSeconds: number, private readonly now: () => number = () => performance.now()) {
    this.elapsedMs = initialSeconds * 1000;
  }

  start() {
    if (this.startedAt === null) this.startedAt = this.now();
  }

  pause() {
    if (this.startedAt === null) return;
    this.elapsedMs += Math.max(0, this.now() - this.startedAt);
    this.startedAt = null;
  }

  seconds() {
    const current = this.startedAt === null ? 0 : Math.max(0, this.now() - this.startedAt);
    return Math.floor((this.elapsedMs + current) / 1000);
  }
}
