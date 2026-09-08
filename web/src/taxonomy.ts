import type { TaxonomyTerm } from "./types";

export interface TaxonomyIndex {
  terms: readonly TaxonomyTerm[];
  byId: Map<string, TaxonomyTerm>;
  children: Map<string, string[]>;
  roots: string[];
  searchText: Map<string, string>;
}
export interface OutlineRow { term: TaxonomyTerm; depth: number }

export function buildTaxonomy(terms: readonly TaxonomyTerm[]): TaxonomyIndex {
  const byId = new Map(terms.map((term) => [term.id, term]));
  const children = new Map<string, string[]>();
  for (const term of terms) {
    for (const parent of term.parents) {
      const list = children.get(parent) ?? [];
      list.push(term.id);
      children.set(parent, list);
    }
  }
  const roots = terms.filter((term) => !term.parents.some((id) => byId.has(id))).map((term) => term.id);
  const reached = new Set<string>();
  const walk = (root: string) => {
    const pending = [root];
    while (pending.length) {
      const id = pending.pop()!;
      if (reached.has(id)) continue;
      reached.add(id);
      pending.push(...(children.get(id) ?? []));
    }
  };
  roots.forEach(walk);
  // A disconnected cycle has no natural root; keep it browsable without inventing an edge.
  for (const term of terms) if (!reached.has(term.id)) { roots.push(term.id); walk(term.id); }
  const searchText = new Map(terms.map((term) => [term.id,
    [term.id, term.uri, term.label, term.definition ?? "", ...term.synonyms].join(" ").toLowerCase()]));
  return { terms, byId, children, roots, searchText };
}

export function searchTaxonomy(index: TaxonomyIndex, query: string): readonly TaxonomyTerm[] {
  const words = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  return index.terms.filter((term) => words.every((word) => index.searchText.get(term.id)?.includes(word)));
}

export function outline(index: TaxonomyIndex, expanded: ReadonlySet<string>): OutlineRow[] {
  const seen = new Set<string>();
  const rows: OutlineRow[] = [];
  const pending = [...index.roots].reverse().map((id) => ({ id, depth: 0 }));
  while (pending.length) {
    const { id, depth } = pending.pop()!;
    const term = index.byId.get(id);
    if (!term || seen.has(id)) continue;
    seen.add(id);
    rows.push({ term, depth });
    if (expanded.has(id)) {
      for (const child of [...(index.children.get(id) ?? [])].reverse()) pending.push({ id: child, depth: depth + 1 });
    }
  }
  return rows;
}

export function ancestorIds(index: TaxonomyIndex, id: string): Set<string> {
  const seen = new Set<string>();
  const pending = [...(index.byId.get(id)?.parents ?? [])];
  while (pending.length) {
    const parent = pending.pop()!;
    if (seen.has(parent)) continue;
    seen.add(parent);
    pending.push(...(index.byId.get(parent)?.parents ?? []));
  }
  return seen;
}
