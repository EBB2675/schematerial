import { describe, expect, it } from "vitest";

import { scrollToIndex, visibleRange } from "./virtual";

describe("visibleRange", () => {
  it("renders a window bounded by the viewport, not by the element count", () => {
    const small = visibleRange(0, 600, 30, 800);
    const huge = visibleRange(0, 600, 30, 400_000);
    expect(huge.end - huge.start).toBe(small.end - small.start);
    expect(huge.end - huge.start).toBeLessThan(60);
  });

  it("reserves the full scroll height", () => {
    expect(visibleRange(0, 600, 30, 1000).total).toBe(30_000);
  });

  it("offsets the rendered slice to its scroll position", () => {
    const window = visibleRange(3000, 600, 30, 1000, 0);
    expect(window.start).toBe(100);
    expect(window.offset).toBe(3000);
  });

  it("overscans above the fold without going negative", () => {
    const window = visibleRange(0, 600, 30, 1000, 6);
    expect(window.start).toBe(0);
    expect(window.offset).toBe(0);
  });

  it("clamps past the end and past the beginning", () => {
    const past = visibleRange(10_000_000, 600, 30, 100);
    expect(past.end).toBe(100);
    expect(past.start).toBeLessThan(100);
    expect(visibleRange(-500, 600, 30, 100).start).toBe(0);
  });

  it("renders nothing for an empty list or an unmeasured viewport", () => {
    expect(visibleRange(0, 600, 30, 0)).toEqual({ start: 0, end: 0, offset: 0, total: 0 });
    expect(visibleRange(0, 0, 30, 500).end).toBe(0);
  });
});

describe("scrollToIndex", () => {
  it("leaves an already visible row alone", () => {
    expect(scrollToIndex(5, 0, 600, 30)).toBeNull();
  });

  it("scrolls up to a row above the fold and down to one below it", () => {
    expect(scrollToIndex(2, 300, 600, 30)).toBe(60);
    expect(scrollToIndex(30, 0, 600, 30)).toBe(330);
  });
});
