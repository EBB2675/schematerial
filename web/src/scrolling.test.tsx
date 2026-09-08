// @vitest-environment jsdom
/**
 * What a scroll frame costs, measured rather than asserted as an adjective.
 *
 * The claim is that scrolling either side does no work proportional to the
 * number of elements in its schema. Three things are measured here:
 *
 * 1. how many rows are rendered, at a realistic size and at a hundred times it;
 * 2. how many times a scroll re-filters the index or rebuilds its searchable
 *    text -- which must be never, not merely rarely;
 * 3. what a scroll event actually costs at both sizes, compared as a ratio.
 *
 * A ratio is used instead of a millisecond budget on purpose: an absolute
 * timing threshold turns into a flaky test on a loaded machine, while work that
 * became proportional to the element count would show up here as a factor of a
 * hundred, not a factor of two.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Provider } from "react-redux";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { api } from "./api";
import { createStore, type AppStore } from "./store";
import type { IndexRow, SchemaSummary } from "./types";

const counters = vi.hoisted(() => ({ filter: 0, haystacks: 0 }));

// Wrapping rather than replacing: the real filtering runs, and every call to it
// is counted.
vi.mock("./search", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./search")>();
  return {
    ...actual,
    buildHaystacks: (...args: Parameters<typeof actual.buildHaystacks>) => {
      counters.haystacks += 1;
      return actual.buildHaystacks(...args);
    },
    filterElements: (...args: Parameters<typeof actual.filterElements>) => {
      counters.filter += 1;
      return actual.filterElements(...args);
    },
  };
});

const SMALL = 1_000;
const LARGE = 100_000;
const NOMAD = "nomad_general";
const BAM = "bam_object_types";

function summary(name: string, pkg: string, count: number): SchemaSummary {
  return {
    name,
    title: name,
    status: "ok",
    error: null,
    schema_id: `https://w3id.org/schematerial/${name}`,
    source: { package: pkg, version: "1.0.0", dependencies: null },
    toolchain: null,
    cache_key: "k",
    counts: {
      classes: 1,
      local_attributes: count,
      effective_attributes: count,
      inherited_attributes: 0,
      enums: 0,
      browsable_elements: count,
      snapshot_paths: count,
    },
    diagnostics: { total: 0 },
    schema_diagnostics: [],
  };
}

function rows(prefix: string, count: number): IndexRow[] {
  const built: IndexRow[] = [];
  for (let index = 0; index < count; index += 1) {
    built.push({
      id: `${prefix}:Pkg%2EClass${index % 400}.field_${index}`,
      kind: index % 50 === 0 ? "class" : "attribute",
      name: `field_${index}`,
      class_id: `${prefix}:Pkg%2EClass${index % 400}`,
      class_name: `Class${index % 400}`,
      range: "float",
      unit: index % 3 === 0 ? "J" : null,
      inherited: index % 7 === 0,
      multivalued: false,
      diagnostics: index % 11 === 0 ? 1 : 0,
      snapshot_paths: 1,
    });
  }
  return built;
}

/**
 * Both indexes are put straight into the query cache, so the measurement is of
 * rendering and scrolling alone and no request is involved at all.
 */
function seed(count: number): AppStore {
  const store = createStore();
  store.dispatch(
    api.util.upsertQueryData("catalogue", undefined, {
      schemas: [summary(NOMAD, "nomad-simulations", count), summary(BAM, "bam-masterdata", count)],
    }),
  );
  store.dispatch(
    api.util.upsertQueryData("elements", NOMAD, {
      schema: NOMAD,
      elements: rows("nomadsim", count),
    }),
  );
  store.dispatch(
    api.util.upsertQueryData("elements", BAM, { schema: BAM, elements: rows("bammd", count) }),
  );
  return store;
}

const positions = new WeakMap<Element, number>();

beforeEach(() => {
  counters.filter = 0;
  counters.haystacks = 0;
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  // jsdom lays nothing out, so both the viewport height and the scroll position
  // have to be supplied for a virtualised list to be exercised at all.
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    value: 600,
  });
  Object.defineProperty(HTMLElement.prototype, "scrollTop", {
    configurable: true,
    get(this: Element) {
      return positions.get(this) ?? 0;
    },
    set(this: Element, value: number) {
      positions.set(this, value);
    },
  });
  // Any request would be a failure of the seeding above, not a passing test.
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("the measurement must not reach the network"))),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function mount(count: number): Promise<HTMLElement[]> {
  const store = seed(count);
  render(
    <Provider store={store}>
      <App />
    </Provider>,
  );
  const lists = await screen.findAllByRole("listbox");
  await waitFor(() => expect(rendered(lists[0] as HTMLElement)).toBeGreaterThan(0));
  return lists;
}

function rendered(list: HTMLElement): number {
  return within(list).queryAllByRole("option").length;
}

/** The first row currently rendered, which is how far the window has travelled. */
function firstRow(list: HTMLElement): string {
  return within(list).queryAllByRole("option")[0]?.textContent ?? "";
}

/** One scroll event per iteration, at a position that keeps moving. */
function burst(lists: HTMLElement[], times: number): number {
  const start = performance.now();
  for (let index = 0; index < times; index += 1) {
    for (const list of lists) {
      fireEvent.scroll(list, { target: { scrollTop: 600 + index * 313 } });
    }
  }
  return performance.now() - start;
}

describe("what a scroll frame costs", () => {
  it("renders a window bounded by the viewport, not by the schema size", async () => {
    const small = await mount(SMALL);
    const smallRendered = small.map(rendered);
    cleanup();
    const large = await mount(LARGE);
    const largeRendered = large.map(rendered);

    // Two sides, both windowed, both the same at a hundred times the size.
    expect(smallRendered).toHaveLength(2);
    expect(largeRendered).toEqual(smallRendered);
    for (const count of largeRendered) {
      // A real slice, and a bounded one: the viewport holds 20 rows plus overscan.
      expect(count).toBeGreaterThan(20);
      expect(count).toBeLessThan(60);
    }
  });

  it("neither refilters nor rebuilds the searchable text while scrolling", async () => {
    const lists = await mount(LARGE);
    const settled = { ...counters };
    const started = lists.map(firstRow);
    burst(lists, 100);

    // The window really travelled; otherwise there would be nothing to measure.
    expect(lists.map(firstRow)).not.toEqual(started);

    // 200 scroll events across two sides of 100,000 elements each, and the index
    // was not touched once.
    expect(counters.filter).toBe(settled.filter);
    expect(counters.haystacks).toBe(settled.haystacks);
    for (const list of lists) expect(rendered(list)).toBeLessThan(60);
  });

  it("costs the same per scroll at a hundred times the elements", async () => {
    const small = await mount(SMALL);
    burst(small, 40); // warm up
    const smallCost = burst(small, 200) / 200;
    cleanup();

    const large = await mount(LARGE);
    burst(large, 40);
    const largeCost = burst(large, 200) / 200;

    // Work proportional to the element count would show here as a factor of a
    // hundred. The bound is deliberately loose so only that fails it.
    const ratio = largeCost / Math.max(smallCost, 0.0001);
    expect(ratio, `small ${smallCost.toFixed(4)}ms, large ${largeCost.toFixed(4)}ms`).toBeLessThan(
      8,
    );
  });

  it("filters each side once per keystroke, whatever the schema size", async () => {
    const user = userEvent.setup();
    await mount(LARGE);
    const before = counters.filter;
    await user.type(screen.getByLabelText("shared search"), "f");

    // Both sides refilter, and neither does it more than a couple of times: the
    // count does not grow with the 200,000 rows behind them.
    await waitFor(() => expect(counters.filter).toBeGreaterThan(before));
    expect(counters.filter - before).toBeLessThanOrEqual(4);
  });
});
