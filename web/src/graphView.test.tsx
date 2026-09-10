// @vitest-environment jsdom
/**
 * The class graph, per side, driven against the payload the server prepares.
 *
 * The properties under test are the ones that make a graph trustworthy rather
 * than decorative: every edge stays inside one schema, a class keeps the
 * position it was given at ingestion no matter what is selected, and selecting
 * a class is selecting the same element the list would have selected.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Provider } from "react-redux";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { createStore } from "./store";
import type { SchemaGraph } from "./types";

const NOMAD = "nomad_fixture";
const BAM = "bam_fixture";
const BASE = "nomadsim:Pkg%2EBase";
const CHILD = "nomadsim:Pkg%2EChild";
const EXTRA = "nomadsim:Pkg%2EExtra";
const ROOT = "nomadsim:Pkg%2ERoot";
const BAM_CLASS = "bammd:Object%2ESample";

function summary(name: string, pkg: string, classes: number) {
  return {
    name,
    module: name,
    title: name,
    status: "ok",
    error: null,
    schema_id: `https://w3id.org/schematerial/${name}`,
    source: { package: pkg, version: "1.0.0", dependencies: null },
    toolchain: null,
    cache_key: "k",
    counts: {
      classes,
      local_attributes: classes,
      effective_attributes: classes,
      inherited_attributes: 0,
      enums: 0,
      browsable_elements: classes,
      snapshot_paths: classes,
    },
    diagnostics: { total: 0 },
    schema_diagnostics: [],
  };
}

function classRow(id: string, name: string) {
  return {
    id,
    kind: "class",
    name,
    class_id: id,
    class_name: name,
    range: null,
    unit: null,
    inherited: false,
    multivalued: false,
    diagnostics: 0,
    snapshot_paths: 1,
  };
}

function attributeRow(id: string, name: string, classId: string, className: string, unit = "J") {
  return {
    id,
    kind: "attribute",
    name,
    class_id: classId,
    class_name: className,
    range: "float",
    unit,
    inherited: false,
    multivalued: false,
    diagnostics: 0,
    snapshot_paths: 1,
  };
}

const NOMAD_ELEMENTS = [
  classRow(BASE, "Base"),
  attributeRow(`${BASE}.value`, "value", BASE, "Base"),
  classRow(CHILD, "Child"),
  classRow(EXTRA, "Extra"),
  attributeRow(`${EXTRA}.tag`, "tag", EXTRA, "Extra", "K"),
  classRow(ROOT, "Root"),
];

const BAM_ELEMENTS = [classRow(BAM_CLASS, "Sample")];

// Positions as the server lays them out: bases on top, subclasses below.
const NOMAD_GRAPH: SchemaGraph = {
  schema: NOMAD,
  nodes: [
    { id: BASE, key: "Pkg.Base", name: "Base", x: 0, y: 0, attributes: 1, diagnostics: 0 },
    { id: EXTRA, key: "Pkg.Extra", name: "Extra", x: 240, y: 0, attributes: 1, diagnostics: 0 },
    { id: ROOT, key: "Pkg.Root", name: "Root", x: 480, y: 0, attributes: 1, diagnostics: 2 },
    { id: CHILD, key: "Pkg.Child", name: "Child", x: 0, y: 130, attributes: 2, diagnostics: 0 },
  ],
  edges: [
    { id: "is_a:Pkg.Child->Pkg.Base", source: CHILD, target: BASE, kind: "is_a", label: null },
    { id: "mixin:Pkg.Child->Pkg.Extra", source: CHILD, target: EXTRA, kind: "mixin", label: null },
    {
      id: "contains:Pkg.Root.child->Pkg.Child",
      source: ROOT,
      target: CHILD,
      kind: "contains",
      label: "child",
    },
  ],
  width: 720,
  height: 260,
};

const BAM_GRAPH: SchemaGraph = {
  schema: BAM,
  nodes: [
    {
      id: BAM_CLASS,
      key: "Object.Sample",
      name: "Sample",
      x: 0,
      y: 0,
      attributes: 1,
      diagnostics: 0,
    },
  ],
  edges: [],
  width: 240,
  height: 130,
};

const INDEXES: Record<string, unknown[]> = { [NOMAD]: NOMAD_ELEMENTS, [BAM]: BAM_ELEMENTS };
const GRAPHS: Record<string, SchemaGraph> = { [NOMAD]: NOMAD_GRAPH, [BAM]: BAM_GRAPH };

// The class box size the component declares to React Flow.
const BOX = { width: 180, height: 36 };

let requests: string[] = [];

function respond(url: string): Response {
  const target = new URL(url);
  requests.push(target.pathname + target.search);
  if (target.pathname === "/api/schemas") {
    return Response.json({
      schemas: [summary(NOMAD, "nomad-simulations", 4), summary(BAM, "bam-masterdata", 1)],
    });
  }
  const elements = target.pathname.match(/^\/api\/schemas\/([^/]+)\/elements$/);
  if (elements !== null) {
    const name = elements[1] ?? "";
    return Response.json({ schema: name, elements: INDEXES[name] ?? [] });
  }
  const graph = target.pathname.match(/^\/api\/schemas\/([^/]+)\/graph$/);
  if (graph !== null) {
    const found = GRAPHS[graph[1] ?? ""];
    if (found === undefined) return new Response("{}", { status: 404 });
    return Response.json(found);
  }
  if (/^\/api\/schemas\/[^/]+\/element$/.test(target.pathname)) {
    return Response.json({
      kind: "class",
      id: target.searchParams.get("id"),
      schema: NOMAD,
      key: "Pkg.Child",
      name: "Child",
      description: "A converted section.",
      parents: [],
      ancestors: [],
      counts: {
        local_attributes: 0,
        effective_attributes: 0,
        inherited_attributes: 0,
        snapshot_paths: 0,
      },
      attributes: [],
      snapshot: null,
      snapshot_paths: [],
      diagnostics: [],
      source_version: "1.0.0",
    });
  }
  return new Response("{}", { status: 404 });
}

beforeEach(() => {
  requests = [];
  // jsdom lays nothing out, and a graph library needs measurements to place an
  // edge between two boxes at all. The observer reports the size the component
  // declares for a class box, so edges are drawn here as they are in a browser.
  vi.stubGlobal(
    "ResizeObserver",
    class {
      callback: ResizeObserverCallback;
      constructor(callback: ResizeObserverCallback) {
        this.callback = callback;
      }
      observe(target: Element) {
        this.callback(
          [{ target, contentRect: BOX } as unknown as ResizeObserverEntry],
          this as unknown as ResizeObserver,
        );
      }
      unobserve() {}
      disconnect() {}
    },
  );
  // jsdom implements no SVG geometry, and an edge label measures itself.
  Object.defineProperty(SVGElement.prototype, "getBBox", {
    configurable: true,
    value: () => ({ x: 0, y: 0, width: 40, height: 12 }),
  });
  vi.stubGlobal(
    "DOMMatrixReadOnly",
    class {
      m22 = 1;
      constructor(_transform?: string) {}
    },
  );
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    value: 600,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    value: BOX.height,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    value: BOX.width,
  });
  Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
    configurable: true,
    value: () => ({
      x: 0,
      y: 0,
      top: 0,
      left: 0,
      right: BOX.width,
      bottom: BOX.height,
      ...BOX,
    }),
  });
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(respond(typeof input === "string" ? input : (input as Request).url)),
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mount() {
  return render(
    <Provider store={createStore()}>
      <App />
    </Provider>,
  );
}

function pane(side: "left" | "right"): HTMLElement {
  return screen.getByRole("region", { name: `${side} side` });
}

/** Switch one side to the graph and wait for its nodes. */
async function showGraph(side: "left" | "right", user: ReturnType<typeof userEvent.setup>) {
  const views = within(pane(side)).getByRole("group", { name: `view on the ${side}` });
  await user.click(within(views).getByRole("button", { name: "graph" }));
  await waitFor(() => expect(nodes(side).length).toBeGreaterThan(0));
}

function nodes(side: "left" | "right"): HTMLElement[] {
  return Array.from(pane(side).querySelectorAll(".react-flow__node"));
}

function nodeFor(side: "left" | "right", name: string): HTMLElement {
  const found = nodes(side).find((node) => node.textContent === name);
  if (found === undefined) throw new Error(`no class box named ${name}`);
  return found;
}

/**
 * Click a class box.
 *
 * A bare click, not a pointer sequence: pressing down on the canvas is how a
 * reader starts panning it, and the pan handler reads `event.view.document`,
 * which a browser fills in and jsdom leaves null. Selecting a class is what
 * these tests are about, and a click is all that takes.
 */
function clickNode(side: "left" | "right", name: string) {
  fireEvent.click(nodeFor(side, name));
}

function placement(side: "left" | "right"): Record<string, string> {
  const at: Record<string, string> = {};
  for (const node of nodes(side)) {
    at[node.textContent ?? ""] = node.style.transform;
  }
  return at;
}

describe("the class graph", () => {
  it("draws one box per class and keeps the list's identifiers", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    await showGraph("left", user);

    expect(nodes("left").map((node) => node.textContent).sort()).toEqual([
      "Base",
      "Child",
      "Extra",
      "Root",
    ]);
    // A node is addressed by the class element identifier, the same one the
    // list selects and the detail endpoint is asked for.
    expect(nodeFor("left", "Child").getAttribute("data-id")).toBe(CHILD);
  });

  it("keeps every edge inside one schema", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    await showGraph("left", user);
    await showGraph("right", user);

    const own = new Set(NOMAD_GRAPH.nodes.map((node) => node.id));
    for (const edge of NOMAD_GRAPH.edges) {
      expect(own.has(edge.source) && own.has(edge.target)).toBe(true);
    }
    // Two graphs on screen, and the one with no structure draws no edges.
    expect(pane("left").querySelectorAll(".react-flow__edge").length).toBe(3);
    expect(pane("right").querySelectorAll(".react-flow__edge").length).toBe(0);
  });

  it("distinguishes a backbone parent from a mixin and names a containment", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    await showGraph("left", user);

    const edges = pane("left").querySelectorAll(".react-flow__edge");
    const kinds = Array.from(edges).map((edge) => edge.getAttribute("class") ?? "");
    expect(kinds.some((name) => name.includes("is_a"))).toBe(true);
    expect(kinds.some((name) => name.includes("mixin"))).toBe(true);
    expect(kinds.some((name) => name.includes("contains"))).toBe(true);
    // The containment edge says which attribute holds the other class.
    expect(within(pane("left")).getByText("child")).toBeDefined();
  });

  it("does not move a class when the selection changes", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    await showGraph("left", user);
    const before = placement("left");

    clickNode("left", "Child");
    await waitFor(() =>
      expect(nodeFor("left", "Child").className).toContain("selected"),
    );
    expect(placement("left")).toEqual(before);

    clickNode("left", "Root");
    await waitFor(() => expect(nodeFor("left", "Root").className).toContain("selected"));
    // Every box, not only the two that were clicked, is where it started.
    expect(placement("left")).toEqual(before);
  });

  it("does not move a class when the search changes", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    await showGraph("left", user);
    const before = placement("left");

    await user.type(screen.getByLabelText("shared search"), "Child");
    await waitFor(() => expect(nodeFor("left", "Base").className).toContain("dimmed"));
    expect(placement("left")).toEqual(before);
    // Dimmed, never removed: an absent class would silently cut the edges
    // running through it.
    expect(nodes("left")).toHaveLength(4);
    expect(nodeFor("left", "Child").className).toContain("lit");
  });

  it("highlights a class whose attribute matched, not only its own name", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    await showGraph("left", user);

    // `tag` is an attribute of Extra; the class it belongs to lights up.
    await user.type(screen.getByLabelText("shared search"), "tag");
    await waitFor(() => expect(nodeFor("left", "Extra").className).toContain("lit"));
    expect(nodeFor("left", "Base").className).toContain("dimmed");
  });

  it("selects the same element the list would, and shows it in the detail panel", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    await showGraph("left", user);
    clickNode("left", "Child");

    await within(pane("left")).findByText("A converted section.");
    expect(pane("left").querySelector(".identifier")?.textContent).toBe(CHILD);
    // The footer reports it as that side's current selection.
    const bar = screen.getByRole("contentinfo", { name: "selected on each side" });
    expect(within(bar).getByText(CHILD)).toBeDefined();
  });

  it("keeps the selection when the side switches back to the list", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    await showGraph("left", user);
    clickNode("left", "Child");
    await waitFor(() => expect(nodeFor("left", "Child").className).toContain("selected"));

    const views = within(pane("left")).getByRole("group", { name: "view on the left" });
    await user.click(within(views).getByRole("button", { name: "list" }));
    const list = await within(pane("left")).findByRole("listbox");
    const selected = within(list)
      .getAllByRole("option")
      .filter((row) => row.getAttribute("aria-selected") === "true");
    expect(selected).toHaveLength(1);
    expect(selected[0]?.textContent).toContain("Child");
  });

  it("lets one side show a graph while the other shows a list", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    await showGraph("left", user);

    expect(within(pane("left")).queryByRole("listbox")).toBeNull();
    expect(within(pane("right")).getByRole("listbox")).toBeDefined();
    expect(nodes("right")).toHaveLength(0);
  });

  it("moves the selection through the graph with the keyboard", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    await showGraph("left", user);

    const canvas = within(pane("left")).getByRole("application", {
      name: /class graph .*left side/,
    });
    canvas.focus();
    await user.keyboard("{ArrowDown}");
    await waitFor(() => expect(nodeFor("left", "Base").className).toContain("selected"));
    await user.keyboard("{End}");
    await waitFor(() => expect(nodeFor("left", "Child").className).toContain("selected"));
  });

  it("fetches one graph per schema and none while searching", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    await showGraph("left", user);
    const after = requests.filter((url) => url.endsWith("/graph")).length;

    await user.type(screen.getByLabelText("shared search"), "child");
    fireEvent.wheel(pane("left").querySelector(".react-flow__pane") as Element, { deltaY: -100 });
    expect(requests.filter((url) => url.endsWith("/graph"))).toHaveLength(after);
    expect(after).toBe(1);
  });

  it("gives the graph most of the column, and more of it than a list gets", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    // The split only divides anything once there is a detail to divide with,
    // so pick a class first -- on the graph, where the boxes are laid out.
    await showGraph("left", user);
    clickNode("left", "Child");
    await user.click(
      within(within(pane("left")).getByRole("group", { name: "view on the left" })).getByRole(
        "button",
        { name: "list" },
      ),
    );
    const asList = Number(
      within(pane("left")).getByRole("separator").getAttribute("aria-valuenow"),
    );
    await showGraph("left", user);
    const asGraph = Number(
      within(pane("left")).getByRole("separator").getAttribute("aria-valuenow"),
    );

    // A canvas needs room before it reads as one; a detail panel does not.
    expect(asGraph).toBeGreaterThan(asList);
    expect(asGraph).toBeGreaterThanOrEqual(70);
    expect(pane("left").querySelector(".region")?.getAttribute("style")).toContain(
      `${asGraph}%`,
    );
  });

  it("lets the reader take more height for the graph", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    await showGraph("left", user);
    clickNode("left", "Child");
    const splitter = within(pane("left")).getByRole("separator");
    const before = Number(splitter.getAttribute("aria-valuenow"));

    splitter.focus();
    await user.keyboard("{ArrowDown}{ArrowDown}");
    const after = Number(splitter.getAttribute("aria-valuenow"));
    expect(after).toBeGreaterThan(before);
    expect(pane("left").querySelector(".detail-region")?.getAttribute("style")).toContain(
      `${100 - after}%`,
    );

    // Double-clicking hands the division back to the default for this view.
    fireEvent.doubleClick(splitter);
    await waitFor(() =>
      expect(Number(splitter.getAttribute("aria-valuenow"))).toBe(before),
    );
  });

  it("gives one side the whole window and hands it back on Escape", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    await showGraph("left", user);

    await user.click(screen.getByLabelText("expand the left side"));
    await waitFor(() => expect(screen.queryByLabelText("right side")).toBeNull());
    // Still the same graph, not a second one built for a bigger space.
    expect(nodes("left")).toHaveLength(4);

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.getByLabelText("right side")).toBeDefined());
    expect(screen.getByLabelText("expand the left side")).toBeDefined();
  });

  it("keeps the schema counts behind a disclosure and reports the graph's own", async () => {
    const user = userEvent.setup();
    mount();
    await waitFor(() => expect(within(pane("left")).getByRole("listbox")).toBeDefined());
    const disclosure = within(pane("left"))
      .getByLabelText(/^counts and diagnostics/)
      .closest("details") as HTMLDetailsElement;
    expect(disclosure.open).toBe(false);

    await showGraph("left", user);
    // Switching view does not put seven totals back on the canvas's header.
    expect(disclosure.open).toBe(false);
    // The counts that matter on a canvas are reported next to it.
    expect(within(pane("left")).getByText(/4 classes · 3 structural edges/)).toBeDefined();
  });

  it("offers no graph for a side whose import was refused", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          Response.json({
            schemas: [
              {
                ...summary(NOMAD, "nomad-simulations", 0),
                status: "unsupported",
                error: "Incomplete extraction",
                schema_diagnostics: [],
              },
            ],
          }),
        ),
      ),
    );
    mount();
    await screen.findByText("This schema was not accepted as a faithful import");
    // No view toggle at all: there is nothing faithful to draw.
    expect(screen.queryByRole("group", { name: "view on the left" })).toBeNull();
  });
});
