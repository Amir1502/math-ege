import { describe, expect, it } from 'vitest';
import { ActiveClock } from '../src/learning/active-clock';

describe('cumulative task active time', () => {
  it('does not count a hidden tab or a route the task has left', () => {
    let time = 0;
    const clock = new ActiveClock(8, () => time);
    clock.start();
    time = 2500;
    clock.pause();
    expect(clock.seconds()).toBe(10);
    time = 100_000;
    expect(clock.seconds()).toBe(10);
    clock.start();
    time = 101_000;
    expect(clock.seconds()).toBe(11);
  });
  it('is safe against repeated visibility events', () => {
    let time = 0;
    const clock = new ActiveClock(0, () => time);
    clock.start();
    time = 1000;
    clock.start();
    time = 2000;
    clock.pause();
    clock.pause();
    expect(clock.seconds()).toBe(2);
  });
});
