/**
 * Fixed-height list windowing.
 *
 * The number of rows rendered depends on the viewport, never on how many
 * elements the schema has. That is the property the aligner panes need in order
 * to scroll a large schema without per-frame work proportional to its size.
 */

export interface ListWindow {
  /** First row index to render. */
  start: number;
  /** One past the last row index to render. */
  end: number;
  /** Pixel offset of `start`, used to position the rendered slice. */
  offset: number;
  /** Full scroll height the spacer must reserve. */
  total: number;
}

export function visibleRange(
  scrollTop: number,
  viewportHeight: number,
  rowHeight: number,
  count: number,
  overscan = 6,
): ListWindow {
  const total = count * rowHeight;
  if (count <= 0 || rowHeight <= 0 || viewportHeight <= 0) {
    return { start: 0, end: 0, offset: 0, total: Math.max(0, total) };
  }
  const top = Math.min(Math.max(scrollTop, 0), Math.max(0, total - viewportHeight));
  const first = Math.max(0, Math.floor(top / rowHeight) - overscan);
  const span = Math.ceil(viewportHeight / rowHeight) + overscan * 2 + 1;
  const start = Math.min(first, Math.max(0, count - 1));
  const end = Math.min(count, start + span);
  return { start, end, offset: start * rowHeight, total };
}

/** The scroll position that brings `index` fully into view, or null if it already is. */
export function scrollToIndex(
  index: number,
  scrollTop: number,
  viewportHeight: number,
  rowHeight: number,
): number | null {
  const top = index * rowHeight;
  const bottom = top + rowHeight;
  if (top < scrollTop) return top;
  if (bottom > scrollTop + viewportHeight) return bottom - viewportHeight;
  return null;
}
