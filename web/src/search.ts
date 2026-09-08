/**
 * Filtering over the downloaded element index.
 *
 * Search never reaches the network: the server hands over one compact index at
 * load, and every keystroke filters it here. The searchable text for a row is
 * built once per index rather than once per keystroke.
 */

import type { IndexRow } from "./types";

export type KindFilter = "all" | "class" | "attribute";

export interface Filters {
  query: string;
  kind: KindFilter;
  onlyInherited: boolean;
  onlyDiagnostics: boolean;
}

export const EMPTY_FILTERS: Filters = {
  query: "",
  kind: "all",
  onlyInherited: false,
  onlyDiagnostics: false,
};

/** Searchable text for one row: its name, its class, the dotted pair, range and unit. */
export function haystack(row: IndexRow): string {
  return [
    row.name,
    row.class_name,
    `${row.class_name}.${row.name}`,
    row.range ?? "",
    row.unit ?? "",
  ]
    .join(" ")
    .toLowerCase();
}

export function buildHaystacks(rows: readonly IndexRow[]): string[] {
  return rows.map(haystack);
}

export function tokenize(query: string): string[] {
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter((token) => token.length > 0);
}

/** Every token must appear somewhere in the row's text, in any order. */
export function filterElements(
  rows: readonly IndexRow[],
  filters: Filters,
  haystacks?: readonly string[],
): IndexRow[] {
  const tokens = tokenize(filters.query);
  const result: IndexRow[] = [];
  for (let index = 0; index < rows.length; index += 1) {
    const row = rows[index];
    if (row === undefined) continue;
    if (filters.kind !== "all" && row.kind !== filters.kind) continue;
    if (filters.onlyInherited && !row.inherited) continue;
    if (filters.onlyDiagnostics && row.diagnostics === 0) continue;
    if (tokens.length > 0) {
      const text = haystacks?.[index] ?? haystack(row);
      if (!tokens.every((token) => text.includes(token))) continue;
    }
    result.push(row);
  }
  return result;
}
