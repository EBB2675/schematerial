import { describe, expect, it } from "vitest";

import { buildHaystacks, filterElements, tokenize } from "./search";
import type { IndexRow } from "./types";

function row(overrides: Partial<IndexRow> & Pick<IndexRow, "id" | "name">): IndexRow {
  return {
    kind: "attribute",
    class_id: "nomadsim:Pkg%2ESimulation",
    class_name: "Simulation",
    range: null,
    unit: null,
    inherited: false,
    multivalued: false,
    diagnostics: 0,
    snapshot_paths: 0,
    ...overrides,
  };
}

const ROWS: IndexRow[] = [
  row({ id: "nomadsim:Pkg%2ESimulation", name: "Simulation", kind: "class" }),
  row({ id: "nomadsim:Pkg%2ESimulation.name", name: "name", range: "string" }),
  row({
    id: "nomadsim:Pkg%2ESimulation.total_energy",
    name: "total_energy",
    range: "float",
    unit: "J",
    inherited: true,
    diagnostics: 2,
  }),
  row({
    id: "nomadsim:Pkg%2ECell.positions",
    name: "positions",
    class_name: "Cell",
    class_id: "nomadsim:Pkg%2ECell",
    range: "double",
  }),
];

const ALL = { query: "", kind: "all" as const, onlyInherited: false, onlyDiagnostics: false };

describe("tokenize", () => {
  it("drops empty tokens and lowercases", () => {
    expect(tokenize("  Total   ENERGY ")).toEqual(["total", "energy"]);
    expect(tokenize("   ")).toEqual([]);
  });
});

describe("filterElements", () => {
  it("returns everything when nothing is asked for", () => {
    expect(filterElements(ROWS, ALL)).toHaveLength(ROWS.length);
  });

  it("matches every token in any order, case-insensitively", () => {
    const hits = filterElements(ROWS, { ...ALL, query: "energy TOTAL" });
    expect(hits.map((hit) => hit.name)).toEqual(["total_energy"]);
  });

  it("matches the owning class and the dotted pair", () => {
    expect(filterElements(ROWS, { ...ALL, query: "cell" }).map((hit) => hit.name)).toEqual([
      "positions",
    ]);
    expect(
      filterElements(ROWS, { ...ALL, query: "simulation.name" }).map((hit) => hit.name),
    ).toEqual(["name"]);
  });

  it("matches ranges and units", () => {
    expect(filterElements(ROWS, { ...ALL, query: "double" }).map((hit) => hit.name)).toEqual([
      "positions",
    ]);
    expect(filterElements(ROWS, { ...ALL, query: "J" }).map((hit) => hit.name)).toEqual([
      "total_energy",
    ]);
  });

  it("filters by kind, inheritance and diagnostics independently", () => {
    expect(filterElements(ROWS, { ...ALL, kind: "class" }).map((hit) => hit.name)).toEqual([
      "Simulation",
    ]);
    expect(filterElements(ROWS, { ...ALL, onlyInherited: true }).map((hit) => hit.name)).toEqual([
      "total_energy",
    ]);
    expect(filterElements(ROWS, { ...ALL, onlyDiagnostics: true }).map((hit) => hit.name)).toEqual([
      "total_energy",
    ]);
  });

  it("keeps identifiers untouched, so a filtered row is still selectable by id", () => {
    const hits = filterElements(ROWS, { ...ALL, query: "positions" });
    expect(hits[0]?.id).toBe("nomadsim:Pkg%2ECell.positions");
  });

  it("gives the same answer with and without precomputed text", () => {
    const filters = { ...ALL, query: "simulation" };
    expect(filterElements(ROWS, filters, buildHaystacks(ROWS))).toEqual(
      filterElements(ROWS, filters),
    );
  });
});
