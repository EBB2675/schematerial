/**
 * What the crosswalk says about the elements on screen.
 *
 * A row is never rewritten, so an element can appear in a rejection and in an
 * accepted mapping at once. The list shows the strongest thing said about it and
 * the Mappings view keeps every row, because a rejection is a record and hiding
 * it would make the same suggestion look new again.
 */

import type { MappingRow } from "./types";

export type MappingState = "mapped" | "suggested" | "rejected";

const RANK: Record<MappingState, number> = { rejected: 1, suggested: 2, mapped: 3 };

function stateOf(status: MappingRow["review_status"]): MappingState {
  return status === "accepted" ? "mapped" : status;
}

/** The state to mark each element with, keyed by element identifier. */
export function mappingStates(rows: readonly MappingRow[]): Map<string, MappingState> {
  const states = new Map<string, MappingState>();
  for (const row of rows) {
    const state = stateOf(row.review_status);
    for (const id of [row.subject_id, row.object_id]) {
      const current = states.get(id);
      if (current === undefined || RANK[state] > RANK[current]) states.set(id, state);
    }
  }
  return states;
}

/** How many rows sit in each review state, for the Mappings tab and its filters. */
export function countByStatus(rows: readonly MappingRow[]): Record<string, number> {
  const counts: Record<string, number> = { accepted: 0, suggested: 0, rejected: 0 };
  for (const row of rows) counts[row.review_status] = (counts[row.review_status] ?? 0) + 1;
  return counts;
}
