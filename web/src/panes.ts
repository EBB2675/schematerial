/**
 * The two sides of the aligner, and how they are filled in the first place.
 *
 * Kept apart from the store so the opening pair is a pure function over the
 * catalogue: it is the rule that decides what a user sees before touching
 * anything, and it deserves to be read and tested on its own.
 */

import type { SchemaSummary } from "./types";

export type Side = "left" | "right";

export const SIDES: readonly Side[] = ["left", "right"];

export function otherSide(side: Side): Side {
  return side === "left" ? "right" : "left";
}

export function sideLabel(side: Side): string {
  return side === "left" ? "left" : "right";
}

export interface Pair {
  left: string | null;
  right: string | null;
}

/**
 * The pair to open with: two schemas from *different* sources when the server
 * loaded any, so a two-source catalogue lands on a cross-source comparison
 * rather than on two modules of the same package.
 *
 * A refused import is never chosen automatically. It stays reachable through
 * either picker, which shows it with its status, but an interface that opens
 * onto a failed conversion is worse than one that opens onto a usable schema.
 */
export function defaultPair(schemas: readonly SchemaSummary[]): Pair {
  const usable = schemas.filter((schema) => schema.status === "ok");
  const left = usable[0] ?? null;
  if (left === null) {
    // Nothing browsable: show the first schema anyway so its refusal is visible.
    return { left: schemas[0]?.name ?? null, right: null };
  }
  const crossSource = usable.find(
    (schema) =>
      schema.name !== left.name &&
      (schema.source.package === null ||
        left.source.package === null ||
        schema.source.package !== left.source.package),
  );
  const right = crossSource ?? usable.find((schema) => schema.name !== left.name) ?? null;
  return { left: left.name, right: right === null ? null : right.name };
}
