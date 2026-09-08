import { skipToken } from "@reduxjs/toolkit/query/react";
import type { ReactNode } from "react";

import { useElementQuery } from "../api";
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

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <span className="field-value">{children}</span>
    </div>
  );
}

function Json({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="subtle">absent</span>;
  return <pre className="json">{JSON.stringify(value, null, 2)}</pre>;
}

function Diagnostics({ entries }: { entries: Diagnostic[] }) {
  if (entries.length === 0) {
    return (
      <section>
        <h3>Diagnostics</h3>
        <p className="subtle">None reported for this element.</p>
      </section>
    );
  }
  return (
    <section>
      <h3>Diagnostics ({entries.length})</h3>
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
    </section>
  );
}

function Paths({ paths }: { paths: string[] }) {
  return (
    <section>
      <h3>Snapshot paths ({paths.length})</h3>
      <p className="subtle">
        Contextual positions reached from a root through subsections. They are not element
        identifiers: one declaration appears at every path that reaches it.
      </p>
      {paths.length === 0 ? (
        <p className="subtle">
          Not reachable from a root by descending subsections in this document.
        </p>
      ) : (
        <ul className="paths">
          {paths.map((path) => (
            <li key={path}>
              <code>{path}</code>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Snapshot({ snapshot }: { snapshot: ElementSnapshot | null }) {
  if (snapshot === null) return null;
  return (
    <section>
      <h3>Snapshot</h3>
      <Field label="name">{snapshot.name}</Field>
      <Field label="parent">
        {snapshot.parent === null ? <span className="subtle">none</span> : <code>{snapshot.parent}</code>}
      </Field>
      <Field label="range">{snapshot.range ?? <span className="subtle">absent</span>}</Field>
      <Field label="unit">{snapshot.unit ?? <span className="subtle">absent</span>}</Field>
      <Field label="semantic type">
        {snapshot.semantic_type ?? <span className="subtle">not stated by the source</span>}
      </Field>
      <Field label="source version">
        {snapshot.source_version ?? <span className="subtle">absent</span>}
      </Field>
    </section>
  );
}

function Parents({ parents, side }: { parents: ClassParent[]; side: Side }) {
  const dispatch = useAppDispatch();
  return (
    <section>
      <h3>Source parents ({parents.length})</h3>
      <p className="subtle">
        Every direct base in source order. The first becomes the LinkML backbone; the rest become
        mixins. The backbone alone is not the whole inheritance structure.
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
    </section>
  );
}

function ClassPanel({ detail, side }: { detail: ClassDetail; side: Side }) {
  const dispatch = useAppDispatch();
  return (
    <>
      <header className="detail-head">
        <span className="badge kind-class">class</span>
        <h2>{detail.name}</h2>
        <code className="subtle">{detail.key}</code>
        <code className="identifier">{detail.id}</code>
      </header>
      {detail.description !== null && <p className="description">{detail.description}</p>}
      <section>
        <h3>Counts</h3>
        <Field label="declared here">{detail.counts.local_attributes}</Field>
        <Field label="effective attributes">{detail.counts.effective_attributes}</Field>
        <Field label="of them inherited">{detail.counts.inherited_attributes}</Field>
        <Field label="source version">
          {detail.source_version ?? <span className="subtle">absent</span>}
        </Field>
      </section>
      <Parents parents={detail.parents} side={side} />
      <section>
        <h3>All ancestors ({detail.ancestors.length})</h3>
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
      </section>
      <section>
        <h3>Effective attributes ({detail.attributes.length})</h3>
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
      </section>
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
        <h2>{detail.name}</h2>
        <code className="subtle">
          {detail.class.key}.{detail.name}
        </code>
        <code className="identifier">{detail.id}</code>
      </header>
      {detail.description !== null && <p className="description">{detail.description}</p>}
      <section>
        <h3>Provenance</h3>
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
        <Field label="declaration identifier">
          <code>{detail.declaration_id ?? "absent"}</code>
        </Field>
        <Field label="source effective reference">
          {detail.source_reference === null ? (
            <span className="subtle">absent</span>
          ) : (
            <>
              <span className="chip">{detail.source_reference.kind}</span>
              <code>{detail.source_reference.declaring_class_id}</code>
            </>
          )}
        </Field>
      </section>
      <Parents parents={parents} side={side} />
      <section>
        <h3>Type</h3>
        <Field label="range">
          {detail.range === null ? (
            <span className="subtle">absent; the source type is not convertible</span>
          ) : (
            <>
              <code>{detail.range.name}</code> <span className="chip">{detail.range.kind}</span>
              {detail.range.target !== undefined && (
                <button
                  type="button"
                  className="link"
                  onClick={() =>
                    dispatch(selectElement({ side, id: detail.range?.target?.id ?? "" }))
                  }
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
            <span className="subtle">none</span>
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
          {detail.multivalued === null ? <span className="subtle">unset</span> : String(detail.multivalued)}
        </Field>
        <Field label="array">
          {detail.array === null ? (
            <span className="subtle">scalar</span>
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
      </section>
      <section>
        <h3>Facets</h3>
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
      </section>
      <section>
        <h3>Source metadata</h3>
        <Field label="kind">{detail.source.kind ?? <span className="subtle">absent</span>}</Field>
        <Field label="type">
          {detail.source.type === null ? <span className="subtle">absent</span> : <code>{detail.source.type}</code>}
        </Field>
        <Field label="shape">
          {detail.source.shape === null ? <span className="subtle">scalar</span> : <code>{JSON.stringify(detail.source.shape)}</code>}
        </Field>
        {detail.source.annotations !== null && <Json value={detail.source.annotations} />}
      </section>
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
