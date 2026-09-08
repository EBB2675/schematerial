// @vitest-environment jsdom
/**
 * The two-pane aligner, driven against the payload shapes the server produces.
 *
 * These fixtures are written by hand rather than captured from a real schema:
 * they are here to pin the page's behaviour, and a real document belongs in the
 * server's own checks. Two of them come from different source packages and keep
 * their own identifier prefixes, because that is what the two sides are for.
 */

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Provider } from "react-redux";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { createStore } from "./store";

const SCHEMA = "fixture";
const BAM = "bam_fixture";
const REFUSED = "refused";
const BASE_CLASS = "nomadsim:Pkg%2EBase";
const CHILD_CLASS = "nomadsim:Pkg%2EChild";
const MIXIN_CLASS = "nomadsim:Pkg%2EExtra";
const INHERITED = `${CHILD_CLASS}.value`;
const BAM_CLASS = "bammd:Object%2ESample";
const BAM_ATTRIBUTE = `${BAM_CLASS}.value`;

const SUMMARY = {
  name: SCHEMA,
  title: `NOMAD ${SCHEMA}`,
  status: "ok",
  error: null,
  schema_id: "https://w3id.org/schematerial/nomad/fixture",
  source: {
    package: "nomad-simulations",
    version: "0.6.0",
    dependencies: { "nomad-lab": "1.4.0" },
  },
  toolchain: { linkml: "1.11.1" },
  cache_key: "0f0f",
  counts: {
    classes: 3,
    local_attributes: 3,
    effective_attributes: 4,
    inherited_attributes: 1,
    enums: 0,
    browsable_elements: 7,
    snapshot_paths: 11,
  },
  diagnostics: { total: 1, partial: 1 },
  schema_diagnostics: [],
};

const BAM_SUMMARY = {
  ...SUMMARY,
  name: BAM,
  title: `BAM masterdata ${BAM}`,
  schema_id: "https://w3id.org/schematerial/bam/fixture",
  source: { package: "bam-masterdata", version: "0.13.1", dependencies: {} },
  cache_key: "0b0b",
  counts: { ...SUMMARY.counts, classes: 1, browsable_elements: 2, snapshot_paths: 2 },
  diagnostics: { total: 0 },
};

const REFUSED_SUMMARY = {
  ...SUMMARY,
  name: REFUSED,
  title: null,
  status: "unsupported",
  error: "Incomplete NOMAD extraction:\nPkg.Base: unreadable",
  schema_diagnostics: [{ path: "Pkg.Base", status: "skipped", reason: "unreadable" }],
  counts: { ...SUMMARY.counts, browsable_elements: 0 },
};

function attributeRow(id: string, name: string, className: string, extra = {}) {
  return {
    id,
    kind: "attribute",
    name,
    class_id: `nomadsim:Pkg%2E${className}`,
    class_name: className,
    range: "float",
    unit: "J",
    inherited: false,
    multivalued: false,
    diagnostics: 0,
    snapshot_paths: 1,
    ...extra,
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

const CHILD_VALUE = attributeRow(INHERITED, "value", "Child", {
  inherited: true,
  diagnostics: 1,
});

const ELEMENTS = [
  classRow(BASE_CLASS, "Base"),
  attributeRow(`${BASE_CLASS}.value`, "value", "Base"),
  classRow(CHILD_CLASS, "Child"),
  CHILD_VALUE,
  attributeRow(`${CHILD_CLASS}.extra_field`, "extra_field", "Child"),
  classRow(MIXIN_CLASS, "Extra"),
  attributeRow(`${MIXIN_CLASS}.tag`, "tag", "Extra"),
];

// A second source: same shape, its own prefix, its own names.
const BAM_ELEMENTS = [
  classRow(BAM_CLASS, "Sample"),
  {
    ...attributeRow(BAM_ATTRIBUTE, "value", "Sample"),
    class_id: BAM_CLASS,
    class_name: "Sample",
  },
];

const DIAGNOSTIC = {
  path: "Pkg.Base.value",
  status: "partial",
  reason: "symbolic shape retained verbatim; only dimension count is represented",
  inherited: true,
};

const DETAILS: Record<string, unknown> = {
  [CHILD_CLASS]: {
    kind: "class",
    id: CHILD_CLASS,
    schema: SCHEMA,
    key: "Pkg.Child",
    name: "Child",
    description: null,
    parents: [
      { id: BASE_CLASS, key: "Pkg.Base", name: "Base", known: true, role: "is_a", position: 0 },
      {
        id: MIXIN_CLASS,
        key: "Pkg.Extra",
        name: "Extra",
        known: true,
        role: "mixin",
        position: 1,
      },
    ],
    ancestors: [{ id: BASE_CLASS, key: "Pkg.Base", name: "Base", known: true }],
    counts: {
      local_attributes: 1,
      effective_attributes: 2,
      inherited_attributes: 1,
      snapshot_paths: 1,
    },
    attributes: [CHILD_VALUE],
    snapshot: null,
    snapshot_paths: [],
    diagnostics: [],
    source_version: "0.6.0",
  },
  [INHERITED]: {
    kind: "attribute",
    id: INHERITED,
    schema: SCHEMA,
    name: "value",
    class: { id: CHILD_CLASS, key: "Pkg.Child", name: "Child", known: true },
    declared_in: { id: BASE_CLASS, key: "Pkg.Base", name: "Base", known: true },
    inherited: true,
    declaration_id: `${BASE_CLASS}.value`,
    source_reference: { kind: "quantity", name: "value", declaring_class_id: "Pkg.Base" },
    description: "An inherited quantity.",
    range: { name: "float", kind: "type" },
    unit: { ucum_code: "J", source: "joule" },
    multivalued: null,
    array: { exact_number_dimensions: 1, dimensions: [] },
    facets: {},
    instantiates: ["smat:NomadShape"],
    source: {
      kind: "quantity",
      type: "builtins.float",
      range: null,
      shape: ["n_atoms"],
      annotations: null,
    },
    snapshot: {
      name: "value",
      parent: "Pkg%2EChild",
      range: "float",
      unit: "J",
      semantic_type: null,
      source_version: "0.6.0",
    },
    snapshot_paths: ["nomadsim:Pkg%2EChild.value"],
    diagnostics: [DIAGNOSTIC],
  },
  [BAM_ATTRIBUTE]: {
    kind: "attribute",
    id: BAM_ATTRIBUTE,
    schema: BAM,
    name: "value",
    class: { id: BAM_CLASS, key: "Object.Sample", name: "Sample", known: true },
    declared_in: { id: BAM_CLASS, key: "Object.Sample", name: "Sample", known: true },
    inherited: false,
    declaration_id: BAM_ATTRIBUTE,
    source_reference: null,
    description: "A masterdata property assignment.",
    range: { name: "float", kind: "type" },
    unit: null,
    multivalued: null,
    array: null,
    facets: {},
    instantiates: [],
    source: { kind: "property", type: "REAL", range: null, shape: null, annotations: null },
    snapshot: null,
    snapshot_paths: [],
    diagnostics: [],
  },
};

const INDEXES: Record<string, unknown[]> = { [SCHEMA]: ELEMENTS, [BAM]: BAM_ELEMENTS };

/** Every request the page made, so "search never reaches the network" is counted. */
let requests: string[] = [];
let catalogue = [SUMMARY, BAM_SUMMARY, REFUSED_SUMMARY];

function respond(url: string): Response {
  const target = new URL(url);
  requests.push(target.pathname + target.search);
  if (target.pathname === "/api/mappings") return Response.json({ rows: [] });
  if (target.pathname === "/api/schemas") {
    return Response.json({ schemas: catalogue });
  }
  const elements = target.pathname.match(/^\/api\/schemas\/([^/]+)\/elements$/);
  if (elements !== null) {
    const name = elements[1] ?? "";
    const rows = INDEXES[name];
    if (rows === undefined) return new Response("{}", { status: 404 });
    return Response.json({ schema: name, elements: rows });
  }
  if (/^\/api\/schemas\/[^/]+\/element$/.test(target.pathname)) {
    const detail = DETAILS[target.searchParams.get("id") ?? ""];
    if (detail === undefined) return new Response("{}", { status: 404 });
    return Response.json(detail);
  }
  return new Response("{}", { status: 404 });
}

beforeEach(() => {
  requests = [];
  catalogue = [SUMMARY, BAM_SUMMARY, REFUSED_SUMMARY];
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  // jsdom does not lay out, so the virtualiser would measure a zero viewport.
  Object.defineProperty(HTMLElement.prototype, "clientHeight", {
    configurable: true,
    value: 600,
  });
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) =>
      Promise.resolve(respond(typeof input === "string" ? input : (input as Request).url)),
    ),
  );
});

afterEach(() => {
  // Vitest globals are off, so Testing Library's automatic cleanup is too.
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

function options(side: "left" | "right"): HTMLElement[] {
  return within(within(pane(side)).getByRole("listbox")).getAllByRole("option");
}

function identifier(side: "left" | "right"): string | undefined {
  return pane(side).querySelector(".identifier")?.textContent ?? undefined;
}

function selectedIn(side: "left" | "right"): HTMLElement[] {
  return options(side).filter((row) => row.getAttribute("aria-selected") === "true");
}

/** Both sides listed, both indexes fetched. */
async function bothSides() {
  mount();
  await waitFor(() => expect(options("left").length).toBe(ELEMENTS.length));
  await waitFor(() => expect(options("right").length).toBe(BAM_ELEMENTS.length));
}

describe("choosing what appears on either side", () => {
  it("opens with one schema from each source, one per side", async () => {
    await bothSides();
    // The header names the source and the module, not the whole dotted path.
    expect(screen.getByRole("heading", { name: "NOMAD · fixture" })).toBeDefined();
    expect(screen.getByRole("heading", { name: "BAM masterdata · bam_fixture" })).toBeDefined();
    // Each side keeps the prefix its own adapter wrote.
    expect(options("left")[0]?.textContent).toContain("Base");
    expect(options("right")[0]?.textContent).toContain("Sample");
    const left = screen.getByLabelText("schema on the left") as HTMLSelectElement;
    const right = screen.getByLabelText("schema on the right") as HTMLSelectElement;
    expect(left.value).toBe(SCHEMA);
    expect(right.value).toBe(BAM);
    // Every loaded schema is offered on either side, refused ones included.
    for (const picker of [left, right]) {
      const values = Array.from(picker.options).map((option) => option.value);
      expect(values).toEqual(["", SCHEMA, BAM, REFUSED]);
    }
  });

  it("re-points one side without disturbing the other", async () => {
    const user = userEvent.setup();
    await bothSides();
    await user.click(options("left")[3] as HTMLElement);
    await waitFor(() => expect(identifier("left")).toBe(INHERITED));

    await user.selectOptions(screen.getByLabelText("schema on the right"), SCHEMA);
    await waitFor(() => expect(options("right").length).toBe(ELEMENTS.length));
    // The left side kept its schema and its selection.
    expect(identifier("left")).toBe(INHERITED);
    expect(selectedIn("left")).toHaveLength(1);
    // The right side dropped a selection that named an element of another schema.
    expect(selectedIn("right")).toHaveLength(0);
  });

  it("closes a side and gives the page back to one schema", async () => {
    const user = userEvent.setup();
    await bothSides();
    await user.selectOptions(screen.getByLabelText("schema on the right"), "");
    await waitFor(() => expect(within(pane("right")).queryByRole("listbox")).toBeNull());
    expect(within(pane("left")).getByRole("listbox")).toBeDefined();
    expect(screen.getAllByRole("listbox")).toHaveLength(1);
    // Reopening it is the same picker; there is no second interface to enter.
    await user.selectOptions(screen.getByLabelText("schema on the right"), BAM);
    await waitFor(() => expect(options("right").length).toBe(BAM_ELEMENTS.length));
  });

  it("allows the same schema on both sides, marks it, and fetches its index once", async () => {
    const user = userEvent.setup();
    await bothSides();
    const before = requests.filter((url) => url === `/api/schemas/${SCHEMA}/elements`).length;
    await user.selectOptions(screen.getByLabelText("schema on the right"), SCHEMA);
    await waitFor(() => expect(options("right").length).toBe(ELEMENTS.length));

    expect(screen.getByText(/schema compared with itself/)).toBeDefined();
    // One index in the cache serves both sides.
    expect(requests.filter((url) => url === `/api/schemas/${SCHEMA}/elements`)).toHaveLength(
      before,
    );
  });

  it("shows a refused import on the side that chose it and leaves the other browsable", async () => {
    const user = userEvent.setup();
    await bothSides();
    await user.selectOptions(screen.getByLabelText("schema on the right"), REFUSED);

    const refused = pane("right");
    expect(
      await within(refused).findByText("This schema was not accepted as a faithful import"),
    ).toBeDefined();
    expect(within(refused).getByText(/Incomplete NOMAD extraction/)).toBeDefined();
    expect(within(refused).getByText("unreadable")).toBeDefined();
    // No element list on that side, and no pretence that it has one.
    expect(within(refused).queryByRole("listbox")).toBeNull();
    expect(options("left").length).toBe(ELEMENTS.length);
  });
});

describe("searching across the two sides", () => {
  it("filters both sides from one search box, without reaching the network", async () => {
    const user = userEvent.setup();
    await bothSides();
    const before = requests.length;

    await user.type(screen.getByLabelText("shared search"), "value");
    await waitFor(() => expect(options("left").length).toBe(2));
    await waitFor(() => expect(options("right").length).toBe(1));
    // Five keystrokes, no request.
    expect(requests.length).toBe(before);
  });

  it("lets one side search on its own while the other keeps following", async () => {
    const user = userEvent.setup();
    await bothSides();
    await user.type(screen.getByLabelText("shared search"), "value");
    await waitFor(() => expect(options("right").length).toBe(1));

    await user.click(screen.getByLabelText("search the right side on its own"));
    const own = await screen.findByLabelText("search the right side");
    // Unlinking carries the current search across, so nothing on screen jumps.
    expect((own as HTMLInputElement).value).toBe("value");

    await user.clear(own);
    await waitFor(() => expect(options("right").length).toBe(BAM_ELEMENTS.length));
    // The shared search still filters the side that is still following it.
    expect(options("left").length).toBe(2);
  });

  it("filters on kind independently once a side has its own search", async () => {
    const user = userEvent.setup();
    await bothSides();
    await user.click(screen.getByLabelText("search the left side on its own"));
    const kinds = screen.getByRole("group", { name: "element kind, search the left side" });
    await user.click(within(kinds).getByRole("button", { name: "classes" }));

    await waitFor(() => expect(options("left").length).toBe(3));
    expect(options("right").length).toBe(BAM_ELEMENTS.length);
  });
});

describe("identifiers", () => {
  it("keeps a side's selected identifier through filtering and scrolling", async () => {
    const user = userEvent.setup();
    await bothSides();
    await user.click(options("left")[3] as HTMLElement);
    await screen.findByText("An inherited quantity.");
    expect(identifier("left")).toBe(INHERITED);

    const search = screen.getByLabelText("shared search");
    await user.type(search, "value");
    await waitFor(() => expect(options("left").length).toBe(2));
    expect(identifier("left")).toBe(INHERITED);

    // A filter that excludes the selection does not change what is selected.
    await user.clear(search);
    await user.type(search, "tag");
    await waitFor(() => expect(options("left").length).toBe(1));
    expect(identifier("left")).toBe(INHERITED);

    await user.clear(search);
    await waitFor(() => expect(options("left").length).toBe(ELEMENTS.length));
    const list = within(pane("left")).getByRole("listbox");
    list.scrollTop = 900;
    list.dispatchEvent(new Event("scroll", { bubbles: true }));
    list.scrollTop = 0;
    list.dispatchEvent(new Event("scroll", { bubbles: true }));
    // Same element, same identifier, after filtering and scrolling.
    expect(identifier("left")).toBe(INHERITED);
    expect(selectedIn("left")[0]?.textContent).toContain("value");
  });

  it("never sends one side's identifier to the other side's schema", async () => {
    const user = userEvent.setup();
    await bothSides();
    await user.click(options("left")[3] as HTMLElement);
    await waitFor(() => expect(identifier("left")).toBe(INHERITED));
    await user.click(options("right")[1] as HTMLElement);
    await waitFor(() => expect(identifier("right")).toBe(BAM_ATTRIBUTE));

    // Each side asks its own schema for its own identifiers, and the two
    // prefixes never cross.
    for (const url of requests.filter((entry) => entry.includes("/element?"))) {
      const asked = new URL(url, "http://localhost");
      const schema = asked.pathname.split("/")[3];
      const id = asked.searchParams.get("id") ?? "";
      expect(id.startsWith(schema === SCHEMA ? "nomadsim:" : "bammd:")).toBe(true);
    }
  });

  it("inspects each side separately, so both provenances can be read at once", async () => {
    const user = userEvent.setup();
    await bothSides();
    await user.click(options("left")[3] as HTMLElement);
    await user.click(options("right")[1] as HTMLElement);

    const left = within(pane("left"));
    const right = within(pane("right"));
    await left.findByText("An inherited quantity.");
    await right.findByText("A masterdata property assignment.");
    // Declaration provenance on the left, still visible while the right is read.
    expect(left.getByText("declared in")).toBeDefined();
    expect(left.getByText(`${BASE_CLASS}.value`)).toBeDefined();
    expect(left.getByText(DIAGNOSTIC.reason)).toBeDefined();
    expect(left.getByText("reported at the declaration")).toBeDefined();
    // Both source parents of the owning class, with their roles.
    expect(await left.findByText("is_a")).toBeDefined();
    expect(left.getByText("mixin")).toBeDefined();
  });

  it("reports both selections together without claiming anything about them", async () => {
    const user = userEvent.setup();
    await bothSides();
    const strip = screen.getByRole("contentinfo", { name: "selected on each side" });

    // Nothing can be authored from an incomplete pair.
    expect(
      (within(strip).getByRole("button", { name: "Create mapping" }) as HTMLButtonElement).disabled,
    ).toBe(true);

    await user.click(options("left")[3] as HTMLElement);
    await user.click(options("right")[1] as HTMLElement);

    // Both identifiers exactly as stored, each readable and each copyable.
    await waitFor(() => expect(within(strip).getByText(INHERITED)).toBeDefined());
    expect(within(strip).getByText(BAM_ATTRIBUTE)).toBeDefined();
    expect(within(strip).getByText("Child.value")).toBeDefined();
    expect(within(strip).getByText("Sample.value")).toBeDefined();
    expect(within(strip).getAllByRole("button", { name: /^copy the/ })).toHaveLength(2);

    // The strip reads left to right until someone turns it round, and it still
    // only reports a selection: the draft starts on the explicit action.
    expect(within(strip).getAllByText(/^(subject|object)$/).map((node) => node.textContent)).toEqual(
      ["subject", "object"],
    );
    expect(
      (within(strip).getByRole("button", { name: "Create mapping" }) as HTMLButtonElement).disabled,
    ).toBe(false);
    expect(screen.queryByRole("dialog", { name: "mapping authoring" })).toBeNull();
  });

  it("turns the pair round before any form is opened", async () => {
    const user = userEvent.setup();
    await bothSides();
    await user.click(options("left")[3] as HTMLElement);
    await user.click(options("right")[1] as HTMLElement);
    const strip = screen.getByRole("contentinfo", { name: "selected on each side" });

    function ends(): string[] {
      return Array.from(strip.querySelectorAll(".strip-end")).map(
        (node) => node.querySelector(".strip-id")?.textContent ?? "",
      );
    }
    await waitFor(() => expect(ends()).toEqual([INHERITED, BAM_ATTRIBUTE]));
    await user.click(within(strip).getByRole("button", { name: "swap subject and object" }));
    expect(ends()).toEqual([BAM_ATTRIBUTE, INHERITED]);
  });
});

describe("the keyboard across two sides", () => {
  it("drives the side that has the keyboard and leaves the other alone", async () => {
    const user = userEvent.setup();
    await bothSides();
    within(pane("left")).getByRole("listbox").focus();
    await user.keyboard("{ArrowDown}{ArrowDown}");

    expect(selectedIn("left")).toHaveLength(1);
    expect(selectedIn("left")[0]?.textContent).toContain("value");
    expect(selectedIn("right")).toHaveLength(0);
  });

  it("moves between the sides and keeps each side's selection", async () => {
    const user = userEvent.setup();
    await bothSides();
    within(pane("left")).getByRole("listbox").focus();
    await user.keyboard("{ArrowDown}");
    const leftFirst = selectedIn("left")[0]?.textContent;

    // `]` hands the keyboard to the right side, which then takes the arrows.
    await user.keyboard("]");
    await waitFor(() =>
      expect(document.activeElement).toBe(within(pane("right")).getByRole("listbox")),
    );
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(selectedIn("right")).toHaveLength(1);
    expect(selectedIn("right")[0]?.textContent).toContain("value");
    // The unfocused side kept what it had selected.
    expect(selectedIn("left")).toHaveLength(1);
    expect(selectedIn("left")[0]?.textContent).toBe(leftFirst);

    // `[[` is how userEvent types a literal bracket; the page sees one `[`.
    await user.keyboard("[[");
    await waitFor(() =>
      expect(document.activeElement).toBe(within(pane("left")).getByRole("listbox")),
    );
    await user.keyboard("{End}");
    expect(selectedIn("left")[0]?.textContent).toContain("tag");
    expect(selectedIn("right")[0]?.textContent).toContain("value");
  });

  it("gives a side the keyboard when focus arrives there, without seizing it", async () => {
    const user = userEvent.setup();
    await bothSides();
    await user.click(screen.getByLabelText("search the right side on its own"));
    const own = await screen.findByLabelText("search the right side");
    // Hand the keyboard to the left side first, so focus then arrives on a side
    // that is not the active one.
    await user.keyboard("[[");
    await waitFor(() =>
      expect(document.activeElement).toBe(within(pane("left")).getByRole("listbox")),
    );
    await user.click(own);

    // Clicking into that side's own search activated it, and left the caret
    // where it was put rather than throwing it into the list.
    expect(document.activeElement).toBe(own);
    await user.keyboard("value");
    expect((own as HTMLInputElement).value).toBe("value");
    // It is the active side, so it takes the arrows once the list has focus.
    await user.keyboard("{ArrowDown}");
    await waitFor(() => expect(selectedIn("right")).toHaveLength(1));
  });

  it("leaves the bracket keys alone while they are being typed into a search", async () => {
    const user = userEvent.setup();
    await bothSides();
    const search = screen.getByLabelText("shared search");
    await user.click(search);
    await user.keyboard("]");
    expect((search as HTMLInputElement).value).toBe("]");
    expect(document.activeElement).toBe(search);
  });
});

describe("counts", () => {
  it("keeps the counts out of the header until they are asked for", async () => {
    const user = userEvent.setup();
    await bothSides();
    const summary = within(pane("left")).getByLabelText(/^counts and diagnostics/);
    const disclosure = summary.closest("details") as HTMLDetailsElement;

    // Nothing about seven different totals is on screen while a list is read.
    expect(disclosure.open).toBe(false);
    await user.click(summary);
    expect(disclosure.open).toBe(true);

    const counts = new Map(
      Array.from(disclosure.querySelectorAll(".count")).map((node) => [
        node.querySelector("dt")?.textContent ?? "",
        node.querySelector("dd")?.textContent ?? "",
      ]),
    );
    expect(counts.get("classes")).toBe("3");
    expect(counts.get("effective attributes")).toBe("4");
    expect(counts.get("browsable elements")).toBe("7");
    // Snapshot paths are a different number over the same schema, never merged
    // into the element count.
    expect(counts.get("snapshot paths")).toBe("11");
  });

  it("says so when the server started with nothing to show", async () => {
    catalogue = [];
    mount();
    expect(await screen.findByText("The server started with no schemas.")).toBeDefined();
  });
});
