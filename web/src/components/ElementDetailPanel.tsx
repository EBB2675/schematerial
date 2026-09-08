import { skipToken } from "@reduxjs/toolkit/query/react";
import type { ReactNode } from "react";

import { useElementQuery } from "../api";
import { readableKey } from "../format";
import type { Side } from "../panes";
import { useAppDispatch, useAppSelector } from "../store";
import type {
  AttributeDetail,
  ClassDetail,
  ClassParent,
  Diagnostic,
  ElementSnapshot,
} from "../types";
import { selectElement } from "../uiSlice";

import { Copyable } from "./Copyable";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <span className="field-value">{children}</span>
    </div>
  );
}

/** A named section that stays out of the way until it is asked for. */
function Section({
  title,
  count,
  open = false,
  children,
}: {
  title: string;
  count?: number;
  open?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="detail-section" open={open}>
      <summary>
        {title}
        {count !== undefined && <span className="section-count">{count}</span>}
      </summary>
      <div className="detail-section-body">{children}</div>
    </details>
  );
}

function Absent({ what = "absent" }: { what?: string }) {
  return <span className="subtle">{what}</span>;
}

function Json({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <Absent />;
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}

function Diagnostics({ entries }: { entries: Diagnostic[] }) {
  return (
    <Section title="Diagnostics" count={entries.length} open={entries.length > 0}>
      {entries.length === 0 ? (
        <p className="subtle">None reported for this element.</p>
      ) : (
        <ul className="diagnostics">
          {entries.map((entry, index) => (
            <li key={`${entry.path}-${index}`}>
              <span className={`badge status-${entry.status}`}>{entry.status}</span>
              <span>{entry.reason}</span>
              <code className="subtle">{entry.path}</code>
              {entry.inherited === true && (
                <span className="chip inherited">reported at the declaration</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function Paths({ paths }: { paths: string[] }) {
  return (
    <Section title="Snapshot paths" count={paths.length}>
      <p className="subtle">
        Contextual positions reached from a root through subsections. They are not element
        identifiers: one declaration appears at every path that reaches it.
      </p>
      {paths.length === 0 ? (
        <p className="subtle">Not reachable from a root by descending subsections.</p>
      ) : (
        <ul className="paths">
          {paths.map((path) => (
            <li key={path}>
              <code>{path}</code>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function Snapshot({ snapshot }: { snapshot: ElementSnapshot | null }) {
  if (snapshot === null) return null;
  return (
    <Section title="Snapshot">
      <Field label="name">{snapshot.name}</Field>
      <Field label="parent">
        {snapshot.parent === null ? <Absent what="none" /> : <code>{snapshot.parent}</code>}
      </Field>
      <Field label="range">{snapshot.range ?? <Absent />}</Field>
      <Field label="unit">{snapshot.unit ?? <Absent />}</Field>
      <Field label="semantic type">
        {snapshot.semantic_type ?? <Absent what="not stated by the source" />}
      </Field>
      <Field label="source version">{snapshot.source_version ?? <Absent />}</Field>
    </Section>
  );
}

function Parents({ parents, side }: { parents: ClassParent[]; side: Side }) {
  const dispatch = useAppDispatch();
  return (
    <Section title="Source parents" count={parents.length}>
      <p className="subtle">
        Every direct base in source order. The first becomes the LinkML backbone; the rest become
        mixins.
      </p>
      {parents.length === 0 ? (
        <p className="subtle">No source base.</p>
      ) : (
        <ol className="parents">
          {parents.map((parent) => (
            <li key={parent.id}>
              <span className={`badge role-${parent.role}`}>{parent.role}</span>
              <button
                type="button"
                className="link"
                onClick={() => dispatch(selectElement({ side, id: parent.id }))}
              >
                {parent.name}
              </button>
              <code className="subtle">{parent.key}</code>
            </li>
          ))}
        </ol>
      )}
    </Section>
  );
}

/** The identifier line: the exact stored string, readable and copyable. */
function Identity({ id, kind }: { id: string; kind: string }) {
  return (
    <div className="identity">
      <code className="identifier">{id}</code>
      <Copyable value={id} label={`the ${kind} identifier`} />
    </div>
  );
}

function ClassPanel({ detail, side }: { detail: ClassDetail; side: Side }) {
  const dispatch = useAppDispatch();
  return (
    <>
      <header className="detail-head">
        <span className="badge kind-class">class</span>
        <h3 className="detail-title">{detail.name}</h3>
        <code className="subtle detail-key">{readableKey(detail.key)}</code>
      </header>
      <Identity id={detail.id} kind="class" />
      {detail.description !== null && <p className="description">{detail.description}</p>}
      <div className="summary-grid">
        <Field label="declared here">{detail.counts.local_attributes}</Field>
        <Field label="effective">{detail.counts.effective_attributes}</Field>
        <Field label="of them inherited">{detail.counts.inherited_attributes}</Field>
        <Field label="source version">{detail.source_version ?? <Absent />}</Field>
      </div>
      <Parents parents={detail.parents} side={side} />
      <Section title="All ancestors" count={detail.ancestors.length}>
        {detail.ancestors.length === 0 ? (
          <p className="subtle">None.</p>
        ) : (
          <ul className="parents">
            {detail.ancestors.map((ancestor) => (
              <li key={ancestor.id}>
                <button
                  type="button"
                  className="link"
                  onClick={() => dispatch(selectElement({ side, id: ancestor.id }))}
                >
                  {ancestor.name}
                </button>
                <code className="subtle">{ancestor.key}</code>
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section title="Effective attributes" count={detail.attributes.length}>
        <ul className="attribute-list">
          {detail.attributes.map((row) => (
            <li key={row.id}>
              <button
                type="button"
                className="link"
                onClick={() => dispatch(selectElement({ side, id: row.id }))}
              >
                {row.name}
              </button>
              {row.range !== null && <span className="chip">{row.range}</span>}
              {row.unit !== null && <span className="chip unit">{row.unit}</span>}
              {row.inherited && <span className="chip inherited">inherited</span>}
              {row.diagnostics > 0 && <span className="chip warn">{row.diagnostics}</span>}
            </li>
          ))}
        </ul>
      </Section>
      <Diagnostics entries={detail.diagnostics} />
      <Snapshot snapshot={detail.snapshot} />
      <Paths paths={detail.snapshot_paths} />
    </>
  );
}

function AttributePanel({
  detail,
  schema,
  side,
}: {
  detail: AttributeDetail;
  schema: string;
  side: Side;
}) {
  const dispatch = useAppDispatch();
  // The owning class carries the complete parent list; fetch it so provenance
  // can be read without leaving the attribute.
  const owner = useElementQuery({ schema, id: detail.class.id });
  const parents = owner.data?.kind === "class" ? owner.data.parents : [];
  const facets = Object.entries(detail.facets);
  return (
    <>
      <header className="detail-head">
        <span className="badge kind-attribute">attribute</span>
        <h3 className="detail-title">{detail.name}</h3>
        <code className="subtle detail-key">
          {readableKey(detail.class.key)}.{detail.name}
        </code>
      </header>
      <Identity id={detail.id} kind="attribute" />
      {detail.description !== null && <p className="description">{detail.description}</p>}
      <div className="summary-grid">
        <Field label="range">
          {detail.range === null ? <Absent /> : <code>{detail.range.name}</code>}
        </Field>
        <Field label="unit">
          {detail.unit === null ? <Absent what="none" /> : <code>{detail.unit.ucum_code ?? "—"}</code>}
        </Field>
        <Field label="seen on">
          <button
            type="button"
            className="link"
            onClick={() => dispatch(selectElement({ side, id: detail.class.id }))}
          >
            {detail.class.name}
          </button>
        </Field>
        <Field label="declared in">
          <button
            type="button"
            className="link"
            onClick={() => dispatch(selectElement({ side, id: detail.declared_in.id }))}
          >
            {detail.declared_in.name}
          </button>
          {detail.inherited ? (
            <span className="chip inherited">inherited</span>
          ) : (
            <span className="chip">declared here</span>
          )}
        </Field>
      </div>
      <Section title="Provenance">
        <Field label="declaration identifier">
          <code>{detail.declaration_id ?? "absent"}</code>
        </Field>
        <Field label="source effective reference">
          {detail.source_reference === null ? (
            <Absent />
          ) : (
            <>
              <span className="chip">{detail.source_reference.kind}</span>
              <code>{detail.source_reference.declaring_class_id}</code>
            </>
          )}
        </Field>
      </Section>
      <Parents parents={parents} side={side} />
      <Section title="Type">
        <Field label="range">
          {detail.range === null ? (
            <Absent what="absent; the source type is not convertible" />
          ) : (
            <>
              <code>{detail.range.name}</code> <span className="chip">{detail.range.kind}</span>
              {detail.range.target !== undefined && (
                <button
                  type="button"
                  className="link"
                  onClick={() => dispatch(selectElement({ side, id: detail.range?.target?.id ?? "" }))}
                >
                  {detail.range.target.name}
                </button>
              )}
            </>
          )}
        </Field>
        {detail.range?.values !== undefined && (
          <Field label="permissible values">{detail.range.values.join(", ")}</Field>
        )}
        <Field label="unit">
          {detail.unit === null ? (
            <Absent what="none" />
          ) : (
            <>
              <code>{detail.unit.ucum_code ?? "no UCUM code"}</code>
              {detail.unit.source !== null && (
                <span className="subtle"> from source “{detail.unit.source}”</span>
              )}
            </>
          )}
        </Field>
        <Field label="multivalued">
          {detail.multivalued === null ? <Absent what="unset" /> : String(detail.multivalued)}
        </Field>
        <Field label="array">
          {detail.array === null ? (
            <Absent what="scalar" />
          ) : (
            <>
              {detail.array.exact_number_dimensions} dimension(s)
              {detail.array.dimensions.length > 0 &&
                `: ${detail.array.dimensions
                  .map((d) => `${d.alias ?? "?"}=${d.exact_cardinality ?? "?"}`)
                  .join(", ")}`}
            </>
          )}
        </Field>
      </Section>
      <Section title="Facets" count={facets.length}>
        {facets.length === 0 ? (
          <p className="subtle">
            None stated by the source. Facets are never inferred, so an absent facet means the
            source did not state one.
          </p>
        ) : (
          facets.map(([tag, value]) => (
            <Field key={tag} label={tag}>
              {String(value)}
            </Field>
          ))
        )}
        {detail.instantiates.length > 0 && (
          <Field label="instantiates">{detail.instantiates.join(", ")}</Field>
        )}
      </Section>
      <Section title="Source metadata">
        <Field label="kind">{detail.source.kind ?? <Absent />}</Field>
        <Field label="type">
          {detail.source.type === null ? <Absent /> : <code>{detail.source.type}</code>}
        </Field>
        <Field label="shape">
          {detail.source.shape === null ? (
            <Absent what="scalar" />
          ) : (
            <code>{JSON.stringify(detail.source.shape)}</code>
          )}
        </Field>
        {detail.source.annotations !== null && <Json value={detail.source.annotations} />}
      </Section>
      <Diagnostics entries={detail.diagnostics} />
      <Snapshot snapshot={detail.snapshot} />
      <Paths paths={detail.snapshot_paths} />
    </>
  );
}

export function ElementDetailPanel({ side, schema }: { side: Side; schema: string }) {
  const selected = useAppSelector((state) => state.ui.panes[side].selected);
  const { data, isFetching, isError } = useElementQuery(
    selected === null ? skipToken : { schema, id: selected },
  );

  if (selected === null) {
    return (
      <section className="detail empty">
        <p className="subtle">Select an element to inspect it.</p>
      </section>
    );
  }
  if (isError) {
    return (
      <section className="detail">
        <p className="notice error">That element is not in this schema.</p>
        <code className="identifier">{selected}</code>
      </section>
    );
  }
  if (data === undefined) {
    return (
      <section className="detail">
        <p className="subtle">{isFetching ? "Loading…" : "No detail."}</p>
      </section>
    );
  }
  return (
    <section className="detail">
      {data.kind === "class" ? (
        <ClassPanel detail={data} side={side} />
      ) : (
        <AttributePanel detail={data} schema={schema} side={side} />
      )}
    </section>
  );
}
