// @vitest-environment jsdom
/**
 * Manual crosswalk authoring, review and PMDco anchoring, driven through the
 * whole interface rather than through one panel.
 *
 * The properties under test are the ones that make the crosswalk trustworthy:
 * a mapping is directional and the human picks the direction, nothing but an
 * explicit human action produces an accepted row, a rejection stays a row, and
 * an unsaved draft is both visible and hard to lose. The redesign moved where
 * those actions live; none of them became implicit.
 */

import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Provider } from "react-redux";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { App } from "./App";
import { createStore } from "./store";
import type { IndexRow, MappingRow, SchemaSummary } from "./types";
import { selectElement } from "./uiSlice";

const NOMAD = "nomadsim:Sample.value";
const BAM = "bammd:Sample.value";
const SNAPSHOT = {
  name: "value",
  parent: "Sample",
  range: "float",
  unit: null,
  semantic_type: null,
  source_version: "1",
};

let saved: MappingRow[];
let posts: { path: string; body: Record<string, unknown>; token: string | null }[];
let failSave: boolean;
let failMappings: boolean;
let reads: number;
let confirmed: boolean;

function summary(name: string, title: string, pkg: string): SchemaSummary {
  return {
    name,
    title,
    status: "ok",
    error: null,
    schema_id: `https://w3id.org/schematerial/${name}`,
    source: { package: pkg, version: "1.0.0", dependencies: null },
    toolchain: null,
    cache_key: "k",
    counts: {
      classes: 0,
      local_attributes: 1,
      effective_attributes: 1,
      inherited_attributes: 0,
      enums: 0,
      browsable_elements: 1,
      snapshot_paths: 1,
    },
    diagnostics: { total: 0 },
    schema_diagnostics: [],
  };
}

const CATALOGUE = [
  summary("nomad", "NOMAD nomad", "nomad-simulations"),
  summary("bam", "BAM masterdata bam", "bam-masterdata"),
];

function index(id: string): IndexRow {
  return {
    id,
    kind: "attribute",
    name: "value",
    class_id: id.split(".")[0] ?? "",
    class_name: "Sample",
    range: "float",
    unit: null,
    inherited: false,
    multivalued: false,
    diagnostics: 0,
    snapshot_paths: 1,
  };
}

/** Only rows nothing supersedes, which is what the server serves. */
function current(): MappingRow[] {
  return saved.filter((row) => !saved.some((later) => later.supersedes === row.record_id));
}

beforeEach(() => {
  saved = [];
  posts = [];
  failSave = false;
  failMappings = false;
  reads = 0;
  confirmed = true;
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal("confirm", vi.fn(() => confirmed));
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, value: 600 });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const request = input as Request;
      const path = new URL(request.url).pathname;
      if (path === "/api/schemas") return Response.json({ schemas: CATALOGUE });
      if (path === "/api/pmdco")
        return Response.json({
          schema: "pmdco",
          version: "3.1.0",
          version_iri: "https://w3id.org/pmd/co/3.1.0",
          term_count: 2,
          anchor_count: 1,
          terms: [
            {
              id: "https://example.org/Entity",
              uri: "https://example.org/Entity",
              label: "Entity",
              definition: null,
              synonyms: [],
              parents: [],
              anchorable: false,
              deprecated: false,
            },
            {
              id: "pmdco:Material",
              uri: "https://w3id.org/pmd/co/Material",
              label: "Material",
              definition: "Matter used in a process",
              synonyms: ["substance"],
              parents: ["https://example.org/Entity"],
              anchorable: true,
              deprecated: false,
            },
          ],
        });
      if (path === "/api/mappings") {
        reads += 1;
        if (failMappings) return Response.json({}, { status: 503 });
        return Response.json({ rows: current() });
      }
      if (path === "/api/review-session") return Response.json({ token: "session-token" });
      if (path.includes("/elements")) {
        const nomad = path.includes("nomad");
        return Response.json({
          schema: nomad ? "nomad" : "bam",
          elements: [index(nomad ? NOMAD : BAM)],
        });
      }
      if (request.method === "POST") {
        const body = (await request.json()) as Record<string, unknown>;
        posts.push({ path, body, token: request.headers.get("X-Review-Token") });
        if (failSave) {
          return Response.json({ detail: "Disk unavailable; draft not saved" }, { status: 503 });
        }
        if (path.endsWith("/review")) {
          const row = saved.find((entry) => entry.record_id === body.record_id)!;
          const result = {
            ...row,
            record_id: `urn:uuid:row-${saved.length}`,
            supersedes: row.record_id,
            predicate_id: body.predicate_id ?? row.predicate_id,
            review_status: body.action === "accept" ? "accepted" : "rejected",
            author_id: body.author_id,
            comment: body.comment,
          } as MappingRow;
          saved.push(result);
          return Response.json(result);
        }
        const row = {
          ...body,
          record_id: `urn:uuid:row-${saved.length}`,
          review_status: "accepted",
          mapping_date: "2026-09-08",
          mapping_justification: "semapv:ManualMappingCuration",
          subject_snapshot: SNAPSHOT,
          object_snapshot: SNAPSHOT,
        } as unknown as MappingRow;
        saved.push(row);
        return Response.json(row, { status: 201 });
      }
      return Response.json({}, { status: 404 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function mount() {
  const store = createStore();
  render(
    <Provider store={store}>
      <App />
    </Provider>,
  );
  await waitFor(() =>
    expect(
      screen.getAllByRole("listbox").flatMap((list) => within(list).queryAllByRole("option")),
    ).toHaveLength(2),
  );
  await waitFor(() => expect(reads).toBeGreaterThan(0));
  return store;
}

function strip(): HTMLElement {
  return screen.getByRole("contentinfo", { name: "selected on each side" });
}

function drawer(): HTMLElement {
  return screen.getByRole("dialog", { name: "mapping authoring" });
}

function status(): string {
  return screen.getByRole("status").textContent ?? "";
}

async function mappings(user: ReturnType<typeof userEvent.setup>): Promise<HTMLElement> {
  await user.click(screen.getByRole("tab", { name: /Mappings/ }));
  return screen.getByRole("table", { name: "saved mappings" });
}

/** Select on both sides, open the drawer from the strip, and fill the form in. */
async function draft() {
  const user = userEvent.setup();
  await user.click(within(screen.getByRole("listbox", { name: /on the left/ })).getByRole("option"));
  await user.click(
    within(screen.getByRole("listbox", { name: /on the right/ })).getByRole("option"),
  );
  await user.click(within(strip()).getByRole("button", { name: "Create mapping" }));
  await user.type(
    within(drawer()).getByLabelText("Author URI or ORCID"),
    "https://orcid.org/0000-0001-2345-6789",
  );
  await user.type(within(drawer()).getByLabelText("Justification"), "I reviewed the definitions.");
  return user;
}

it.each([
  [false, "narrow"],
  [true, "broad"],
] as const)(
  "authors in the chosen direction and reloads the saved row (%s, %s)",
  async (reverse, predicate) => {
    await mount();
    const user = await draft();
    if (reverse) {
      await user.click(within(drawer()).getByRole("button", { name: "Reverse direction" }));
    }
    await user.selectOptions(
      within(drawer()).getByLabelText("Predicate"),
      `skos:${predicate}Match`,
    );

    // The direction is stated in the drawer before anything is written.
    const direction = within(drawer()).getByLabelText("mapping direction");
    expect(direction.textContent).toContain(reverse ? BAM : NOMAD);
    expect(direction.textContent).toContain(predicate);

    expect(posts).toHaveLength(0);
    expect(status()).toBe("Unsaved changes");
    const leave = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(leave);
    expect(leave.defaultPrevented).toBe(true);

    await user.click(within(drawer()).getByRole("button", { name: "Save accepted mapping" }));
    await waitFor(() => expect(status()).toBe("Saved to the crosswalk."));
    // Nothing is left to edit, so the form gets out of the way of the panes.
    expect(screen.queryByRole("dialog", { name: "mapping authoring" })).toBeNull();
    expect(posts).toHaveLength(1);
    expect(posts[0]?.token).toBe("session-token");
    expect(posts[0]?.body.subject_id).toBe(reverse ? BAM : NOMAD);
    expect(posts[0]?.body.object_id).toBe(reverse ? NOMAD : BAM);
    expect(posts[0]?.body.predicate_id).toBe(`skos:${predicate}Match`);
    // The snapshot is the server's to write from its own prepared record.
    expect(posts[0]?.body).not.toHaveProperty("review_status");
    expect(posts[0]?.body).not.toHaveProperty("subject_snapshot");

    cleanup();
    await mount();
    const user2 = userEvent.setup();
    const table = await mappings(user2);
    await waitFor(() =>
      expect(within(table).getByText("I reviewed the definitions.")).toBeDefined(),
    );
    expect(table.textContent).toContain("https://orcid.org/0000-0001-2345-6789");
    expect(within(table).getByText(predicate)).toBeDefined();
    expect(within(table).getByText("mapped")).toBeDefined();
    // Both mapped elements are marked in the lists they came from.
    await user2.click(screen.getByRole("tab", { name: "Align" }));
    await waitFor(() => expect(screen.getAllByText("mapped")).toHaveLength(2));

    const leavingSaved = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(leavingSaved);
    expect(leavingSaved.defaultPrevented).toBe(false);
  },
);

it("offers all five predicates and says what each direction means", async () => {
  await mount();
  const user = await draft();
  const select = within(drawer()).getByLabelText("Predicate") as HTMLSelectElement;
  expect(Array.from(select.options).map((option) => option.value)).toEqual([
    "skos:exactMatch",
    "skos:closeMatch",
    "skos:relatedMatch",
    "skos:narrowMatch",
    "skos:broadMatch",
  ]);
  await user.selectOptions(select, "skos:narrowMatch");
  expect(within(drawer()).getByText("The object is narrower than the subject.")).toBeDefined();
  await user.selectOptions(select, "skos:broadMatch");
  expect(within(drawer()).getByText("The object is broader than the subject.")).toBeDefined();
  expect(posts).toHaveLength(0);
});

it("keeps the unsaved draft on failure and freezes its endpoints while panes change", async () => {
  const store = await mount();
  const user = await draft();
  act(() => {
    store.dispatch(selectElement({ side: "left", id: "nomadsim:Other" }));
  });
  failSave = true;
  await user.click(within(drawer()).getByRole("button", { name: "Save accepted mapping" }));
  expect(await screen.findByRole("alert")).toBeDefined();
  expect(status()).toBe("Unsaved changes");
  expect(
    (within(drawer()).getByLabelText("Justification") as HTMLTextAreaElement).value,
  ).toBe("I reviewed the definitions.");
  expect(saved).toHaveLength(0);
  // Browsing after the draft was opened did not move its endpoints.
  expect(posts[0]?.body.subject_id).toBe(NOMAD);
  expect(screen.queryByText("mapped")).toBeNull();
  failSave = false;
  await user.click(within(drawer()).getByRole("button", { name: "Save accepted mapping" }));
  await waitFor(() => expect(saved).toHaveLength(1));
});

it("keeps the draft when the drawer is closed and confirms before discarding it", async () => {
  await mount();
  const user = await draft();
  await user.click(within(drawer()).getByRole("button", { name: "close the authoring drawer" }));
  expect(screen.queryByRole("dialog", { name: "mapping authoring" })).toBeNull();
  // The draft is still unsaved, still announced, and still guarded.
  expect(status()).toBe("Unsaved changes");
  const leave = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(leave);
  expect(leave.defaultPrevented).toBe(true);

  // Reopening finds everything that was typed.
  await user.click(within(strip()).getByRole("button", { name: "Create mapping" }));
  expect(
    (within(drawer()).getByLabelText("Justification") as HTMLTextAreaElement).value,
  ).toBe("I reviewed the definitions.");

  // Discarding is confirmed, and a refused confirmation changes nothing.
  confirmed = false;
  await user.click(within(drawer()).getByRole("button", { name: "Discard draft" }));
  expect(status()).toBe("Unsaved changes");
  confirmed = true;
  await user.click(within(drawer()).getByRole("button", { name: "Discard draft" }));
  expect(status()).toBe("No unsaved changes");
  expect(posts).toHaveLength(0);
});

it.each(["accept", "reject"] as const)("requires explicit %s after opening a suggestion", async (action) => {
  saved = [
    {
      record_id: "urn:uuid:suggestion",
      subject_id: NOMAD,
      object_id: BAM,
      predicate_id: "skos:narrowMatch",
      author_id: "https://example.org/tool",
      confidence: 1,
      review_status: "suggested",
      comment: "Candidate",
      mapping_date: "2026-09-08",
      mapping_justification: "semapv:LexicalMatching",
      subject_snapshot: SNAPSHOT,
      object_snapshot: SNAPSHOT,
    },
  ];
  await mount();
  const user = userEvent.setup();
  const table = await mappings(user);
  expect(within(table).getByText("suggested")).toBeDefined();

  await user.click(within(table).getByRole("button", { name: "Review suggestion" }));
  expect(posts).toHaveLength(0);
  await user.type(
    within(drawer()).getByLabelText("Author URI or ORCID"),
    "https://example.org/human",
  );
  await user.type(within(drawer()).getByLabelText("Justification"), "Human rationale");
  // Everything is filled in and nothing has been written.
  expect(posts).toHaveLength(0);

  await user.click(
    within(drawer()).getByRole("button", {
      name: action === "accept" ? "Accept suggestion" : "Reject suggestion",
    }),
  );
  await waitFor(() => expect(posts).toHaveLength(1));
  expect(posts[0]?.path).toBe("/api/human/review");
  expect(posts[0]?.body.action).toBe(action);
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "Review suggestion" })).toBeNull(),
  );
  // The suggestion itself is untouched; the review is a new row that supersedes it.
  expect(saved[0]?.review_status).toBe("suggested");
  expect(saved[1]?.supersedes).toBe(saved[0]?.record_id);
  expect(saved[1]?.review_status).toBe(action === "accept" ? "accepted" : "rejected");
});

it("keeps a rejection as a row and stops marking the elements as mapped", async () => {
  await mount();
  const user = await draft();
  await user.click(within(drawer()).getByRole("button", { name: "Save accepted mapping" }));
  await waitFor(() => expect(saved).toHaveLength(1));
  await waitFor(() => expect(screen.getAllByText("mapped")).toHaveLength(2));

  const table = await mappings(user);
  await user.click(within(table).getByRole("button", { name: "Correct mapping" }));
  await user.type(
    within(drawer()).getByLabelText("Author URI or ORCID"),
    "https://example.org/human",
  );
  await user.type(within(drawer()).getByLabelText("Justification"), "Not the same quantity");
  await user.click(within(drawer()).getByRole("button", { name: "Retract mapping" }));

  await waitFor(() => expect(saved).toHaveLength(2));
  expect(saved[1]?.review_status).toBe("rejected");
  // The rejection is a row, not a deletion.
  await waitFor(() => expect(within(table).getByText("rejected")).toBeDefined());
  expect(within(table).getAllByRole("row")).toHaveLength(2);
  await user.click(screen.getByRole("tab", { name: "Align" }));
  await waitFor(() => expect(screen.queryByText("mapped")).toBeNull());
  expect(screen.getAllByText("rejected")).toHaveLength(2);
});

it("keeps a direct mapping and both PMDco anchors together through the manual workflow", async () => {
  await mount();
  const user = await draft();
  await user.click(within(drawer()).getByRole("button", { name: "Save accepted mapping" }));
  await waitFor(() => expect(saved).toHaveLength(1));

  // The taxonomy is closed until a semantic anchor is asked for.
  expect(screen.queryByRole("complementary", { name: "PMDco taxonomy" })).toBeNull();
  await user.click(within(strip()).getByRole("button", { name: "Add semantic anchor" }));
  const ontology = await screen.findByRole("complementary", { name: "PMDco taxonomy" });

  await user.type(await within(ontology).findByLabelText("Search PMDco"), "substance");
  await user.click(await within(ontology).findByRole("button", { name: "Material" }));
  expect(within(ontology).getByText("Matter used in a process")).toBeDefined();

  for (const side of ["left", "right"] as const) {
    const before = posts.length;
    await user.click(within(ontology).getByRole("button", { name: `Anchor ${side} selection` }));
    expect(posts).toHaveLength(before);
    expect(status()).toBe("Unsaved changes");
    await user.type(
      within(drawer()).getByLabelText("Author URI or ORCID"),
      "https://example.org/human",
    );
    await user.type(
      within(drawer()).getByLabelText("Justification"),
      `Reviewed ${side} PMDco anchor`,
    );
    await user.click(within(drawer()).getByRole("button", { name: "Save accepted mapping" }));
    await waitFor(() => expect(posts).toHaveLength(before + 1));
    expect(posts.at(-1)?.body.subject_id).toBe(side === "left" ? NOMAD : BAM);
    expect(posts.at(-1)?.body.object_id).toBe("pmdco:Material");
    expect(posts.at(-1)?.body.object_schema).toBe("pmdco");
    await waitFor(() => expect(status()).toBe("Saved to the crosswalk."));
  }
  expect(saved).toHaveLength(3);

  cleanup();
  await mount();
  const user2 = userEvent.setup();
  const table = await mappings(user2);
  // The direct mapping and both anchors are shown together.
  await waitFor(() => expect(within(table).getAllByRole("row")).toHaveLength(4));
  expect(table.textContent).toContain("I reviewed the definitions.");
  expect(table.textContent).toContain("Reviewed left PMDco anchor");
  expect(table.textContent).toContain("Reviewed right PMDco anchor");
});

it("browses the taxonomy and labels imported ancestors as context", async () => {
  await mount();
  const user = userEvent.setup();
  await user.click(within(strip()).getByRole("button", { name: "Add semantic anchor" }));
  const ontology = await screen.findByRole("complementary", { name: "PMDco taxonomy" });

  await user.click(await within(ontology).findByRole("button", { name: "Entity (context)" }));
  expect(within(ontology).queryByRole("button", { name: "Anchor left selection" })).toBeNull();
  await user.click(within(ontology).getByRole("button", { name: "Expand Entity" }));
  await user.click(
    within(within(ontology).getByRole("tree")).getByRole("button", { name: "Material" }),
  );
  // Nothing is selected in either pane yet, so neither anchor is offered.
  expect(
    (
      within(ontology).getByRole("button", { name: "Anchor left selection" }) as HTMLButtonElement
    ).disabled,
  ).toBe(true);

  const detail = within(ontology).getByLabelText("selected ontology term");
  await user.click(within(detail).getByRole("button", { name: "Entity" }));
  expect(within(ontology).getByText(/Imported ancestor shown for context/)).toBeDefined();

  await user.type(await within(ontology).findByLabelText("Search PMDco"), "no-such-term");
  expect(await within(ontology).findByText("No terms match this search.")).toBeDefined();
  expect(posts).toHaveLength(0);
});

it("corrects an accepted mapping while keeping its history", async () => {
  await mount();
  const user = await draft();
  await user.click(within(drawer()).getByRole("button", { name: "Save accepted mapping" }));
  await waitFor(() => expect(saved).toHaveLength(1));

  const table = await mappings(user);
  await user.click(within(table).getByRole("button", { name: "Correct mapping" }));
  await user.selectOptions(within(drawer()).getByLabelText("Predicate"), "skos:exactMatch");
  await user.type(
    within(drawer()).getByLabelText("Author URI or ORCID"),
    "https://example.org/human",
  );
  await user.type(within(drawer()).getByLabelText("Justification"), "Correct predicate");
  await user.click(within(drawer()).getByRole("button", { name: "Save accepted correction" }));

  await waitFor(() => expect(saved).toHaveLength(2));
  await waitFor(() => expect(status()).toBe("Saved to the crosswalk."));
  expect(saved[0]?.predicate_id).toBe("skos:closeMatch");
  expect(saved[1]?.predicate_id).toBe("skos:exactMatch");
  expect(saved[1]?.supersedes).toBe(saved[0]?.record_id);
  // The interface shows current records; the file keeps the whole history.
  await waitFor(() => expect(within(table).getByText("exact")).toBeDefined());
  expect(within(table).getAllByRole("row")).toHaveLength(2);
  expect(within(table).queryByText("close")).toBeNull();
});

it("filters the mappings table by review status", async () => {
  saved = [
    {
      record_id: "urn:uuid:suggestion",
      subject_id: NOMAD,
      object_id: BAM,
      predicate_id: "skos:closeMatch",
      author_id: "https://example.org/tool",
      confidence: 0.4,
      review_status: "suggested",
      comment: "Candidate",
      mapping_date: "2026-09-08",
      mapping_justification: "semapv:LexicalMatching",
      subject_snapshot: SNAPSHOT,
      object_snapshot: SNAPSHOT,
    },
  ];
  await mount();
  const user = userEvent.setup();
  const table = await mappings(user);
  expect(within(table).getAllByRole("row")).toHaveLength(2);

  const filters = screen.getByRole("group", { name: "review status" });
  await user.click(within(filters).getByRole("button", { name: /^rejected/ }));
  expect(screen.getByText("No mapping matches this filter.")).toBeDefined();
  await user.click(within(filters).getByRole("button", { name: /^suggested/ }));
  expect(within(screen.getByRole("table", { name: "saved mappings" })).getAllByRole("row"))
    .toHaveLength(2);
});

it("shows the failure rather than an empty table when the store cannot be read", async () => {
  failMappings = true;
  const store = createStore();
  render(
    <Provider store={store}>
      <App />
    </Provider>,
  );
  const user = userEvent.setup();
  await screen.findAllByRole("listbox");
  await user.click(screen.getByRole("tab", { name: /Mappings/ }));
  expect(
    await screen.findByText(/Mappings could not be loaded/),
  ).toBeDefined();
  // An empty table would read as "there are no mappings", which is not what happened.
  expect(screen.queryByRole("table", { name: "saved mappings" })).toBeNull();
});

it("says so when the crosswalk is empty", async () => {
  await mount();
  const user = userEvent.setup();
  await user.click(screen.getByRole("tab", { name: /Mappings/ }));
  expect(
    screen.getByText(/No mappings yet\. In Align, select an element on each side/),
  ).toBeDefined();
  expect(screen.queryByRole("table", { name: "saved mappings" })).toBeNull();
});
