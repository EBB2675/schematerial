// @vitest-environment jsdom
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Provider } from "react-redux";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { CrosswalkPanel } from "./components/CrosswalkPanel";
import { ElementBrowser } from "./components/ElementBrowser";
import { PmdcoPanel } from "./components/PmdcoPanel";
import { createStore } from "./store";
import type { IndexRow, MappingRow } from "./types";
import { chooseSchema, selectElement } from "./uiSlice";

const NOMAD = "nomadsim:Sample.value";
const BAM = "bammd:Sample.value";
const SNAPSHOT = { name: "value", parent: "Sample", range: "float", unit: null,
  semantic_type: null, source_version: "1" };
let saved: MappingRow[];
let posts: { path: string; body: Record<string, unknown>; token: string | null }[];
let failSave: boolean;
let reads: number;

function index(id: string): IndexRow {
  return { id, kind: "attribute", name: "value", class_id: id.split(".")[0] ?? "",
    class_name: "Sample", range: "float", unit: null, inherited: false, multivalued: false,
    diagnostics: 0, snapshot_paths: 1 };
}

beforeEach(() => {
  saved = []; posts = []; failSave = false; reads = 0;
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, value: 600 });
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const request = input as Request;
    const path = new URL(request.url).pathname;
    if (path === "/api/pmdco") return Response.json({
      schema: "pmdco", version: "3.1.0", version_iri: "https://w3id.org/pmd/co/3.1.0",
      term_count: 2, anchor_count: 1, terms: [
        { id: "https://example.org/Entity", uri: "https://example.org/Entity", label: "Entity",
          definition: null, synonyms: [], parents: [], anchorable: false, deprecated: false },
        { id: "pmdco:Material", uri: "https://w3id.org/pmd/co/Material", label: "Material",
          definition: "Matter used in a process", synonyms: ["substance"],
          parents: ["https://example.org/Entity"], anchorable: true, deprecated: false },
      ],
    });
    if (path === "/api/mappings") { reads++; return Response.json({ rows: saved }); }
    if (path === "/api/review-session") return Response.json({ token: "session-token" });
    if (path.includes("/elements")) return Response.json({ schema: path.includes("nomad") ? "nomad" : "bam",
      elements: [index(path.includes("nomad") ? NOMAD : BAM)] });
    if (request.method === "POST") {
      const body = await request.json() as Record<string, unknown>;
      posts.push({ path, body, token: request.headers.get("X-Review-Token") });
      if (failSave) return Response.json({ detail: "Disk unavailable; draft not saved" }, { status: 503 });
      if (path.endsWith("/review")) {
        const row = saved.find((r) => r.record_id === body.record_id)!;
        const result = { ...row, review_status: body.action === "accept" ? "accepted" : "rejected",
          author_id: body.author_id, comment: body.comment } as MappingRow;
        saved = saved.map((r) => r.record_id === result.record_id ? result : r);
        return Response.json(result);
      }
      const row = { ...body, record_id: `urn:uuid:row-${saved.length}`, review_status: "accepted",
        mapping_date: "2026-09-08", mapping_justification: "semapv:ManualMappingCuration",
        subject_snapshot: SNAPSHOT, object_snapshot: SNAPSHOT } as unknown as MappingRow;
      saved.push(row);
      return Response.json(row, { status: 201 });
    }
    return Response.json({}, { status: 404 });
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

async function mount(withOntology = false) {
  const store = createStore();
  store.dispatch(chooseSchema({ side: "left", schema: "nomad" }));
  store.dispatch(chooseSchema({ side: "right", schema: "bam" }));
  render(<Provider store={store}>
    <ElementBrowser side="left" schema="nomad" />
    <ElementBrowser side="right" schema="bam" />
    <CrosswalkPanel />
    {withOntology && <PmdcoPanel />}
  </Provider>);
  await waitFor(() => expect(screen.getAllByRole("listbox").flatMap(
    (list) => within(list).queryAllByRole("option"))).toHaveLength(2));
  await waitFor(() => expect(reads).toBeGreaterThan(0));
  return store;
}

async function draft() {
  const user = userEvent.setup();
  await user.click(within(screen.getByRole("listbox", { name: /on the left/ })).getByRole("option"));
  await user.click(within(screen.getByRole("listbox", { name: /on the right/ })).getByRole("option"));
  await user.click(screen.getByRole("button", { name: "Use selected pair" }));
  await user.type(screen.getByLabelText("Author URI or ORCID"), "https://orcid.org/0000-0001-2345-6789");
  await user.type(screen.getByLabelText("Justification"), "I reviewed the definitions.");
  return user;
}

it.each([[false, "narrow"], [true, "broad"]] as const)(
  "authors in the chosen direction and reloads the saved row (%s, %s)", async (reverse, predicate) => {
    await mount();
    const user = await draft();
    if (reverse) await user.click(screen.getByRole("button", { name: "Reverse direction" }));
    await user.selectOptions(screen.getByLabelText("Predicate"), `skos:${predicate}Match`);
    expect(posts).toHaveLength(0);
    expect(screen.getByRole("status").textContent).toBe("Unsaved changes");
    const leave = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(leave);
    expect(leave.defaultPrevented).toBe(true);
    await user.click(screen.getByRole("button", { name: "Save accepted mapping" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Saved to the crosswalk."));
    expect(posts).toHaveLength(1);
    expect(posts[0]?.token).toBe("session-token");
    expect(posts[0]?.body.subject_id).toBe(reverse ? BAM : NOMAD);
    expect(posts[0]?.body.object_id).toBe(reverse ? NOMAD : BAM);
    expect(posts[0]?.body.predicate_id).toBe(`skos:${predicate}Match`);
    expect(posts[0]?.body).not.toHaveProperty("review_status");
    expect(posts[0]?.body).not.toHaveProperty("subject_snapshot");
    cleanup();
    await mount();
    const records = screen.getByRole("list", { name: "saved mappings" });
    await waitFor(() => expect(within(records).getByText("I reviewed the definitions.")).toBeDefined());
    expect(records.textContent).toContain("https://orcid.org/0000-0001-2345-6789");
    await waitFor(() => expect(screen.getAllByText("mapped")).toHaveLength(2));
    const leavingSaved = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(leavingSaved);
    expect(leavingSaved.defaultPrevented).toBe(false);
  },
);

it("keeps the unsaved draft on failure and freezes its endpoints while panes change", async () => {
  const store = await mount();
  const user = await draft();
  act(() => store.dispatch(selectElement({ side: "left", id: "nomadsim:Other" })));
  failSave = true;
  await user.click(screen.getByRole("button", { name: "Save accepted mapping" }));
  expect(await screen.findByRole("alert")).toBeDefined();
  expect(screen.getByRole("status").textContent).toBe("Unsaved changes");
  expect((screen.getByLabelText("Justification") as HTMLTextAreaElement).value).toBe("I reviewed the definitions.");
  expect(saved).toHaveLength(0);
  expect(posts[0]?.body.subject_id).toBe(NOMAD);
  expect(screen.queryByText("mapped")).toBeNull();
  failSave = false;
  await user.click(screen.getByRole("button", { name: "Save accepted mapping" }));
  await waitFor(() => expect(saved).toHaveLength(1));
});

it.each(["accept", "reject"] as const)("requires explicit %s after opening a suggestion", async (action) => {
  saved = [{ record_id: "urn:uuid:suggestion", subject_id: NOMAD, object_id: BAM,
    predicate_id: "skos:narrowMatch", author_id: "https://example.org/tool", confidence: 1,
    review_status: "suggested", comment: "Candidate", mapping_date: "2026-09-08",
    mapping_justification: "semapv:LexicalMatching", subject_snapshot: SNAPSHOT, object_snapshot: SNAPSHOT }];
  await mount();
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Review suggestion" }));
  expect(posts).toHaveLength(0);
  await user.type(screen.getByLabelText("Author URI or ORCID"), "https://example.org/human");
  await user.type(screen.getByLabelText("Justification"), "Human rationale");
  expect(posts).toHaveLength(0);
  await user.click(screen.getByRole("button", { name: action === "accept" ? "Accept suggestion" : "Reject suggestion" }));
  await waitFor(() => expect(posts).toHaveLength(1));
  expect(posts[0]?.path).toBe("/api/human/review");
  expect(posts[0]?.body.action).toBe(action);
  await waitFor(() => expect(screen.queryByRole("button", { name: "Review suggestion" })).toBeNull());
  expect(saved[0]?.review_status).toBe(action === "accept" ? "accepted" : "rejected");
});


it("keeps a direct mapping and both PMDco anchors together through the manual workflow", async () => {
  await mount(true);
  const user = await draft();
  await user.click(screen.getByRole("button", { name: "Save accepted mapping" }));
  await waitFor(() => expect(saved).toHaveLength(1));
  const ontology = screen.getByRole("complementary", { name: "PMDco taxonomy" });
  const search = within(ontology).getByLabelText("Search PMDco");
  await user.type(search, "substance");
  await user.click(await within(ontology).findByRole("button", { name: "Material" }));
  expect(within(ontology).getByText("Matter used in a process")).toBeDefined();
  for (const side of ["left", "right"] as const) {
    const before = posts.length;
    await user.click(within(ontology).getByRole("button", { name: `Anchor ${side} selection` }));
    expect(posts).toHaveLength(before);
    expect(screen.getByRole("status").textContent).toBe("Unsaved changes");
    await user.type(screen.getByLabelText("Author URI or ORCID"), "https://example.org/human");
    await user.type(screen.getByLabelText("Justification"), `Reviewed ${side} PMDco anchor`);
    await user.click(screen.getByRole("button", { name: "Save accepted mapping" }));
    await waitFor(() => expect(posts).toHaveLength(before + 1));
    expect(posts.at(-1)?.body.subject_id).toBe(side === "left" ? NOMAD : BAM);
    expect(posts.at(-1)?.body.object_id).toBe("pmdco:Material");
    expect(posts.at(-1)?.body.object_schema).toBe("pmdco");
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Saved to the crosswalk."));
  }
  expect(saved).toHaveLength(3);
  cleanup();
  await mount(true);
  const records = screen.getByRole("list", { name: "saved mappings" });
  await waitFor(() => expect(within(records).getAllByRole("listitem")).toHaveLength(3));
  expect(records.textContent).toContain("I reviewed the definitions.");
  expect(records.textContent).toContain("Reviewed left PMDco anchor");
  expect(records.textContent).toContain("Reviewed right PMDco anchor");
});

it("browses the taxonomy and labels imported ancestors as context", async () => {
  await mount(true);
  const user = userEvent.setup();
  const ontology = screen.getByRole("complementary", { name: "PMDco taxonomy" });
  await user.click(await within(ontology).findByRole("button", { name: "Entity (context)" }));
  expect(within(ontology).queryByRole("button", { name: "Anchor left selection" })).toBeNull();
  await user.click(within(ontology).getByRole("button", { name: "Expand Entity" }));
  await user.click(within(within(ontology).getByRole("tree")).getByRole("button", { name: "Material" }));
  expect(within(ontology).getByRole("button", { name: "Anchor left selection" }).hasAttribute("disabled")).toBe(true);
  const detail = within(ontology).getByLabelText("selected ontology term");
  await user.click(within(detail).getByRole("button", { name: "Entity" }));
  expect(within(ontology).getByText(/Imported ancestor shown for context/)).toBeDefined();
  const search = within(ontology).getByLabelText("Search PMDco");
  await user.type(search, "no-such-term");
  expect(await within(ontology).findByText("No terms match this search.")).toBeDefined();
  expect(posts).toHaveLength(0);
});
