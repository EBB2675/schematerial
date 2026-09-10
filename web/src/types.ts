/**
 * Payload shapes served by the preview API.
 *
 * Three identifier kinds appear here and are not interchangeable. `id` names an
 * effective attribute as seen on one class -- that is what the browser lists
 * and selects. `declaration_id` names where the attribute is *declared*, which
 * differs whenever it is inherited. `snapshot_paths` name contextual positions
 * reached by descending from a root, and one declaration has many of them.
 */

export type ElementKind = "class" | "attribute";

export interface Diagnostic {
  path: string;
  status: string;
  reason: string;
  /** True when the diagnostic was reported against an inherited declaration. */
  inherited?: boolean;
}

export interface ClassReference {
  /** Class element identifier. */
  id: string;
  /** Full source definition id, dots unescaped. */
  key: string;
  /** Short source class name. */
  name: string;
  known: boolean;
}

export interface SchemaCounts {
  classes: number;
  local_attributes: number;
  effective_attributes: number;
  inherited_attributes: number;
  enums: number;
  /** Rows in the element index: one per class and per effective attribute. */
  browsable_elements: number;
  /** Contextual positions, not elements. Reported separately on purpose. */
  snapshot_paths: number;
}

export interface SchemaSummary {
  /** Address of this loaded schema, including its version when known. */
  name: string;
  /** Source module path, independent of the schema address. */
  module: string;
  title: string | null;
  status: "ok" | "unsupported";
  error: string | null;
  schema_id: string | null;
  source: {
    package: string | null;
    version: string | null;
    dependencies: Record<string, string> | null;
  };
  toolchain: Record<string, string> | null;
  cache_key: string | null;
  counts: SchemaCounts;
  diagnostics: Record<string, number>;
  schema_diagnostics: Diagnostic[];
}

export interface IndexRow {
  id: string;
  kind: ElementKind;
  name: string;
  class_id: string;
  class_name: string;
  range: string | null;
  unit: string | null;
  inherited: boolean;
  multivalued: boolean;
  diagnostics: number;
  snapshot_paths: number;
}

export interface ElementSnapshot {
  name: string;
  parent: string | null;
  range: string | null;
  unit: string | null;
  semantic_type: string | null;
  source_version: string | null;
}

export interface RangeInfo {
  name: string;
  kind: "class" | "enum" | "type";
  target?: ClassReference;
  values?: string[];
}

export interface SourceReference {
  kind: string;
  name: string;
  declaring_class_id: string;
}

export interface AttributeDetail {
  kind: "attribute";
  id: string;
  schema: string;
  name: string;
  class: ClassReference;
  declared_in: ClassReference;
  inherited: boolean;
  declaration_id: string | null;
  source_reference: SourceReference | null;
  description: string | null;
  range: RangeInfo | null;
  unit: { ucum_code: string | null; source: string | null } | null;
  multivalued: boolean | null;
  array: {
    exact_number_dimensions: number | null;
    dimensions: { alias: string | null; exact_cardinality: number | null }[];
  } | null;
  facets: Record<string, unknown>;
  instantiates: string[];
  source: {
    kind: string | null;
    type: string | null;
    range: unknown;
    shape: unknown;
    annotations: unknown;
  };
  snapshot: ElementSnapshot | null;
  snapshot_paths: string[];
  diagnostics: Diagnostic[];
}

export interface ClassParent extends ClassReference {
  role: "is_a" | "mixin";
  position: number;
}

export interface ClassDetail {
  kind: "class";
  id: string;
  schema: string;
  key: string;
  name: string;
  description: string | null;
  /** Every source parent in source order, not only the backbone one. */
  parents: ClassParent[];
  ancestors: ClassReference[];
  counts: {
    local_attributes: number;
    effective_attributes: number;
    inherited_attributes: number;
    snapshot_paths: number;
  };
  attributes: IndexRow[];
  snapshot: ElementSnapshot | null;
  snapshot_paths: string[];
  diagnostics: Diagnostic[];
  source_version: string | null;
}

export type ElementDetail = AttributeDetail | ClassDetail;

/** How one class is joined to another. Both ends are always classes of the same schema. */
export type EdgeKind = "is_a" | "mixin" | "contains";

export interface GraphNode {
  /** The class element identifier -- the same one the list selects. */
  id: string;
  key: string;
  name: string;
  /** Laid out at ingestion, so a selection or a hover never moves a box. */
  x: number;
  y: number;
  attributes: number;
  diagnostics: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  /** The declaring attribute's name, for a containment edge. */
  label: string | null;
}

export interface SchemaGraph {
  schema: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  width: number;
  height: number;
}

export interface MappingRow {
  supersedes?: string;
  record_id: string;
  subject_id: string;
  object_id: string;
  predicate_id: string;
  mapping_justification: string;
  author_id: string;
  confidence: number;
  review_status: "suggested" | "accepted" | "rejected";
  comment: string;
  mapping_date: string;
  subject_snapshot: ElementSnapshot;
  object_snapshot: ElementSnapshot;
}

export interface TaxonomyTerm {
  id: string;
  uri: string;
  label: string;
  definition: string | null;
  synonyms: string[];
  parents: string[];
  anchorable: boolean;
  deprecated: boolean;
}

export interface PmdcoTaxonomy {
  schema: string;
  version: string;
  version_iri: string;
  term_count: number;
  anchor_count: number;
  terms: TaxonomyTerm[];
  attribution?: string;
  license?: string;
  license_url?: string;
  release_url?: string;
}
