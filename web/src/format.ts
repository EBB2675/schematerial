/**
 * How identifiers and records are said in the interface.
 *
 * The payloads carry exact, unambiguous strings -- a module path, a
 * percent-escaped CURIE, a SKOS predicate URI. Those are what the crosswalk is
 * written in and they stay reachable, but they are not what a reader scans a
 * list with. Everything here turns one of them into a short readable label
 * without ever becoming the value that gets stored.
 */

import type { ElementSnapshot, IndexRow, SchemaSummary } from "./types";

/**
 * The source a schema came from, as a person names it: "NOMAD", "BAM masterdata".
 *
 * The server writes a title of the form "<source> <module>". Taking the source
 * off the front of it keeps the two halves in step with whatever the adapter
 * decided to call itself, instead of holding a second copy of that mapping here.
 */
export function sourceLabel(summary: SchemaSummary): string {
  const title = summary.title ?? "";
  if (title.endsWith(summary.name) && title.length > summary.name.length) {
    return title.slice(0, title.length - summary.name.length).trim();
  }
  return summary.source.package ?? "";
}

/** The last segment of a dotted module path: `…datamodel.object_types` becomes `object_types`. */
export function moduleLabel(summary: SchemaSummary): string {
  const parts = summary.name.split(".");
  return parts[parts.length - 1] ?? summary.name;
}

/** What a pane header calls its schema. The full module path stays one hover away. */
export function schemaLabel(summary: SchemaSummary): string {
  const source = sourceLabel(summary);
  const module = moduleLabel(summary);
  return source === "" ? module : `${source} · ${module}`;
}

/** The source package and version, or an empty string when the source stated neither. */
export function versionLabel(summary: SchemaSummary): string {
  const { package: name, version } = summary.source;
  if (name === null) return version ?? "";
  return version === null ? name : `${name} ${version}`;
}

/** Identifiers escape dots inside a segment; a reader wants them back. */
export function readableKey(value: string): string {
  return value.replace(/%2E/gi, ".");
}

/** An element as a person reads it: the attribute under its class, or the class. */
export function elementLabel(row: IndexRow): string {
  return row.kind === "attribute" ? `${row.class_name}.${row.name}` : row.name;
}

/**
 * A mapping end read from its snapshot, which is the authoritative record of
 * what was mapped. Falls back to the identifier when a row predates a snapshot.
 */
export function snapshotLabel(snapshot: ElementSnapshot | undefined, id: string): string {
  if (snapshot === undefined) return id;
  const parent = snapshot.parent === null ? null : readableKey(snapshot.parent).split(".").pop();
  return parent == null || parent === "" ? snapshot.name : `${parent}.${snapshot.name}`;
}

/** The prefix an identifier carries, which is the source it belongs to. */
export function idPrefix(id: string): string {
  const colon = id.indexOf(":");
  return colon < 0 ? "" : id.slice(0, colon);
}

/**
 * A range as a chip can hold it.
 *
 * A controlled-vocabulary range is a fully qualified module path; the last two
 * segments are what tell one apart from another, and the whole string stays on
 * the row as its title and in the detail below.
 */
export function rangeLabel(range: string): string {
  const parts = range.split(".");
  return parts.length <= 2 ? range : parts.slice(-2).join(".");
}

export const PREDICATES = ["exact", "close", "related", "narrow", "broad"] as const;

/** `skos:narrowMatch` reads as `narrow`; the stored value never changes. */
export function predicateLabel(predicate: string): string {
  return predicate.replace(/^skos:/, "").replace(/Match$/, "");
}

/** How each predicate reads as a sentence about the direction the human chose. */
export function predicateSense(predicate: string): string {
  switch (predicate) {
    case "skos:exactMatch":
      return "The subject and the object mean the same thing.";
    case "skos:closeMatch":
      return "The subject and the object are close enough to interchange with care.";
    case "skos:relatedMatch":
      return "The subject and the object are related without either containing the other.";
    case "skos:narrowMatch":
      return "The object is narrower than the subject.";
    case "skos:broadMatch":
      return "The object is broader than the subject.";
    default:
      return "";
  }
}

/** Review status as shown: an accepted row is a mapping the human stands behind. */
export function statusLabel(status: string): string {
  return status === "accepted" ? "mapped" : status;
}
