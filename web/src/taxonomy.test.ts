import { expect, it } from "vitest";

import { authoringSlice, setSaving, usePair } from "./authoringSlice";
import { ancestorIds, buildTaxonomy, outline, searchTaxonomy } from "./taxonomy";
import type { TaxonomyTerm } from "./types";

function term(id: string, parents: string[] = [], label = id): TaxonomyTerm {
  return { id, uri: `https://example.org/${id}`, label, parents, definition: "A solid specimen",
    synonyms: ["sample"], anchorable: true, deprecated: false };
}

it("retains multiple parents and makes disconnected cycles browsable with bounded traversal", () => {
  const index = buildTaxonomy([term("Root"), term("Parent", ["Root"]),
    term("Child", ["Root", "Parent"]), term("A", ["B"]), term("B", ["A"])]);
  expect(index.roots).toEqual(["Root", "A"]);
  expect(index.children.get("Parent")).toEqual(["Child"]);
  expect(index.children.get("Root")).toEqual(["Parent", "Child"]);
  const all = outline(index, new Set(index.byId.keys()));
  expect(new Set(all.map((row) => row.term.id)).size).toBe(5);
  expect(all).toHaveLength(5);
  expect(ancestorIds(index, "Child")).toEqual(new Set(["Root", "Parent"]));
  expect(ancestorIds(index, "A")).toEqual(new Set(["A", "B"]));
});

it("searches ids, labels, synonyms and definitions without changing stable ids", () => {
  const index = buildTaxonomy([term("pmdco:One", [], "Material")]);
  for (const query of ["PMDCO:ONE", "material", "sample", "solid specimen"]) {
    expect(searchTaxonomy(index, query).map((row) => row.id)).toEqual(["pmdco:One"]);
  }
  expect(searchTaxonomy(index, "not present")).toEqual([]);
});

it("searches a large inline term set in under one second", () => {
  const index = buildTaxonomy(Array.from({ length: 5000 }, (_, i) => term(`pmdco:Term${i}`)));
  const start = performance.now();
  const result = searchTaxonomy(index, "Term4999 sample");
  expect(performance.now() - start).toBeLessThan(1000);
  expect(result.map((t) => t.id)).toEqual(["pmdco:Term4999"]);
});

it("does not replace an in-flight draft when another panel chooses an anchor", () => {
  const original = authoringSlice.reducer(undefined, usePair({
    subject: { schema: "nomad", id: "nomadsim:A" }, object: { schema: "bam", id: "bammd:B" },
  }));
  const pending = authoringSlice.reducer(original, setSaving(true));
  const changed = authoringSlice.reducer(pending, usePair({
    subject: { schema: "nomad", id: "nomadsim:A" }, object: { schema: "pmdco", id: "pmdco:Term" },
  }));
  expect(changed).toEqual(pending);
});
