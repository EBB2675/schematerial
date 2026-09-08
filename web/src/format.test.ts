import { describe, expect, it } from "vitest";

import {
  elementLabel,
  idPrefix,
  moduleLabel,
  predicateLabel,
  readableKey,
  schemaLabel,
  snapshotLabel,
  sourceLabel,
  statusLabel,
  versionLabel,
} from "./format";
import type { ElementSnapshot, IndexRow, SchemaSummary } from "./types";

function summary(over: Partial<SchemaSummary>): SchemaSummary {
  return {
    name: "nomad_simulations.schema_packages.model_method",
    title: "NOMAD nomad_simulations.schema_packages.model_method",
    status: "ok",
    error: null,
    schema_id: null,
    source: { package: "nomad-simulations", version: "0.6.0", dependencies: null },
    toolchain: null,
    cache_key: null,
    counts: {
      classes: 0,
      local_attributes: 0,
      effective_attributes: 0,
      inherited_attributes: 0,
      enums: 0,
      browsable_elements: 0,
      snapshot_paths: 0,
    },
    diagnostics: {},
    schema_diagnostics: [],
    ...over,
  };
}

describe("naming a schema", () => {
  it("takes the source off the title the server wrote", () => {
    expect(sourceLabel(summary({}))).toBe("NOMAD");
    expect(
      sourceLabel(
        summary({
          name: "bam_masterdata.datamodel.object_types",
          title: "BAM masterdata bam_masterdata.datamodel.object_types",
        }),
      ),
    ).toBe("BAM masterdata");
  });

  it("falls back to the source package when the title says nothing extra", () => {
    expect(sourceLabel(summary({ title: null }))).toBe("nomad-simulations");
    expect(sourceLabel(summary({ title: null, source: { package: null, version: null, dependencies: null } }))).toBe("");
  });

  it("names the module by its last segment, and never loses the whole path", () => {
    expect(moduleLabel(summary({}))).toBe("model_method");
    expect(schemaLabel(summary({}))).toBe("NOMAD · model_method");
    // The full dotted path is still the identity; nothing here rewrites it.
    expect(summary({}).name).toBe("nomad_simulations.schema_packages.model_method");
  });

  it("reports the source package and version together, or neither", () => {
    expect(versionLabel(summary({}))).toBe("nomad-simulations 0.6.0");
    expect(versionLabel(summary({ source: { package: "bam-masterdata", version: null, dependencies: null } }))).toBe(
      "bam-masterdata",
    );
    expect(versionLabel(summary({ source: { package: null, version: null, dependencies: null } }))).toBe("");
  });
});

describe("naming an element", () => {
  const row: IndexRow = {
    id: "nomadsim:Pkg%2EChild.value",
    kind: "attribute",
    name: "value",
    class_id: "nomadsim:Pkg%2EChild",
    class_name: "Child",
    range: "float",
    unit: "J",
    inherited: true,
    multivalued: false,
    diagnostics: 0,
    snapshot_paths: 1,
  };

  it("reads an attribute under its class and a class on its own", () => {
    expect(elementLabel(row)).toBe("Child.value");
    expect(elementLabel({ ...row, kind: "class", name: "Child" })).toBe("Child");
  });

  it("unescapes a dotted key for reading without touching the identifier", () => {
    expect(readableKey("Pkg%2EChild")).toBe("Pkg.Child");
    expect(readableKey("Pkg%2eChild")).toBe("Pkg.Child");
    expect(idPrefix(row.id)).toBe("nomadsim");
    expect(idPrefix("no-prefix")).toBe("");
  });

  it("reads a saved row from its snapshot, which is the authoritative record", () => {
    const snapshot: ElementSnapshot = {
      name: "value",
      parent: "Pkg%2EChild",
      range: "float",
      unit: null,
      semantic_type: null,
      source_version: "0.6.0",
    };
    expect(snapshotLabel(snapshot, row.id)).toBe("Child.value");
    expect(snapshotLabel({ ...snapshot, parent: null }, row.id)).toBe("value");
    // A row with no snapshot still says which element it names.
    expect(snapshotLabel(undefined, row.id)).toBe(row.id);
  });
});

describe("naming a predicate and a review state", () => {
  it("shortens the predicate for reading and keeps the stored value elsewhere", () => {
    expect(predicateLabel("skos:narrowMatch")).toBe("narrow");
    expect(predicateLabel("skos:exactMatch")).toBe("exact");
    expect(predicateLabel("smat:somethingElse")).toBe("smat:somethingElse");
  });

  it("says an accepted row is a mapping, and leaves the other two alone", () => {
    expect(statusLabel("accepted")).toBe("mapped");
    expect(statusLabel("suggested")).toBe("suggested");
    expect(statusLabel("rejected")).toBe("rejected");
  });
});
