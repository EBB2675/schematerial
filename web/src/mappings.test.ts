import { expect, it } from "vitest";

import { mappingStates } from "./mappings";
import type { MappingRow } from "./types";

function row(subjectVersion: string | null, objectVersion: string | null, status: MappingRow["review_status"]): MappingRow {
  const snapshot = { name: "value", parent: "Sample", range: null, unit: null, semantic_type: null };
  return {
    record_id: "urn:uuid:fixture",
    subject_id: "nomadsim:Sample.value",
    object_id: "nomadsim:Sample.value",
    predicate_id: "skos:exactMatch",
    mapping_justification: "semapv:ManualMappingCuration",
    author_id: "urn:author:fixture",
    confidence: 1,
    review_status: status,
    comment: "Fixture",
    mapping_date: "2026-09-10",
    subject_snapshot: { ...snapshot, source_version: subjectVersion },
    object_snapshot: { ...snapshot, source_version: objectVersion },
  };
}

it("marks each version independently while keeping precedence within a version", () => {
  const accepted = row("1", "3", "accepted");
  expect(mappingStates([accepted], "1").get(accepted.subject_id)).toBe("mapped");
  expect(mappingStates([accepted], "3").get(accepted.object_id)).toBe("mapped");
  expect(mappingStates([accepted], "5").size).toBe(0);

  const rows = [accepted, row("1", "5", "rejected"), row("1", "5", "suggested")];
  expect(mappingStates(rows, "1").get(accepted.subject_id)).toBe("mapped");
  expect(mappingStates(rows, "5").get(accepted.object_id)).toBe("suggested");
});

it("keeps an unstated version distinct from a stated one", () => {
  const mapping = row(null, "3", "accepted");
  expect(mappingStates([mapping], null).get(mapping.subject_id)).toBe("mapped");
  expect(mappingStates([mapping], "1").size).toBe(0);
});
