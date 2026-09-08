import { useEffect, useMemo, useRef, useState } from "react";

import { usePmdcoQuery } from "../api";
import { usePair } from "../authoringSlice";
import { useAppDispatch, useAppSelector } from "../store";
import { ancestorIds, buildTaxonomy, outline, searchTaxonomy } from "../taxonomy";
import type { TaxonomyTerm } from "../types";
import { visibleRange } from "../virtual";

const EMPTY: TaxonomyTerm[] = [];
const ROW_HEIGHT = 34;

export function PmdcoPanel() {
  const { data, isLoading, isError, refetch } = usePmdcoQuery();
  const dispatch = useAppDispatch();
  const panes = useAppSelector((state) => state.ui.panes);
  const saving = useAppSelector((state) => state.authoring.saving);
  const index = useMemo(() => buildTaxonomy(data?.terms ?? EMPTY), [data]);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const [scroll, setScroll] = useState(0);
  const [height, setHeight] = useState(300);
  const viewport = useRef<HTMLDivElement>(null);
  const searching = query.trim() !== "";
  const rows = useMemo(() => searching
    ? searchTaxonomy(index, query).map((term) => ({ term, depth: 0 }))
    : outline(index, expanded), [index, query, searching, expanded]);
  const term = selected ? index.byId.get(selected) : undefined;
  const windowed = visibleRange(scroll, height, ROW_HEIGHT, rows.length);

  useEffect(() => {
    const node = viewport.current;
    if (!node) return;
    const measure = () => setHeight(node.clientHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [data]);

  function inspect(id: string) {
    setSelected(id);
    setQuery("");
    setExpanded((current) => new Set([...current, ...ancestorIds(index, id)]));
  }
  useEffect(() => {
    const position = rows.findIndex((row) => row.term.id === selected);
    if (position < 0 || !viewport.current) return;
    const node = viewport.current;
    const top = position * ROW_HEIGHT;
    if (top < node.scrollTop || top + ROW_HEIGHT > node.scrollTop + node.clientHeight) {
      node.scrollTop = top;
      setScroll(top);
    }
  }, [selected, rows]);

  function toggle(id: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  return <aside className="pmdco-panel" aria-label="PMDco taxonomy">
    <h2>PMDco {data?.version}</h2>
    {isLoading && <p>Loading the offline taxonomy…</p>}
    {isError && <p role="alert">PMDco could not be loaded. <button onClick={() => void refetch()}>Retry taxonomy</button></p>}
    {data && <>
      <p className="subtle">{data.anchor_count} PMDco terms · available offline</p>
      <label>Search PMDco<input type="search" value={query} onChange={(event) => {
        setQuery(event.target.value); setScroll(0);
        if (viewport.current) viewport.current.scrollTop = 0;
      }} /></label>
      <p className="subtle">{rows.length} {searching ? "results" : "visible terms"}</p>
      <div className="taxonomy-viewport" ref={viewport} role="tree" aria-label="ontology terms" tabIndex={0}
        onScroll={(event) => setScroll(event.currentTarget.scrollTop)}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return;
          const current = rows.findIndex((row) => row.term.id === selected);
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            const next = Math.max(0, Math.min(rows.length - 1, current + (event.key === "ArrowDown" ? 1 : -1)));
            setSelected(rows[next]?.term.id ?? null);
          } else if (event.key === "ArrowRight" && selected && !expanded.has(selected)) {
            event.preventDefault(); toggle(selected);
          } else if (event.key === "ArrowLeft" && selected && expanded.has(selected)) {
            event.preventDefault(); toggle(selected);
          }
        }}>
        <div style={{ height: windowed.total, position: "relative" }}>
          <div style={{ transform: `translateY(${windowed.offset}px)` }}>
            {rows.slice(windowed.start, windowed.end).map(({ term: item, depth }) => {
              const hasChildren = !!index.children.get(item.id)?.length;
              return <div key={item.id} role="treeitem" aria-level={depth + 1}
                aria-selected={selected === item.id} aria-expanded={hasChildren && !searching ? expanded.has(item.id) : undefined}
                className={`taxonomy-row${selected === item.id ? " selected" : ""}`}
                style={{ height: ROW_HEIGHT, paddingLeft: Math.min(depth, 10) * 12 }}>
                {hasChildren && !searching && <button type="button" aria-label={`${expanded.has(item.id) ? "Collapse" : "Expand"} ${item.label}`}
                  onClick={() => toggle(item.id)}>{expanded.has(item.id) ? "−" : "+"}</button>}
                <button type="button" className="taxonomy-name" onClick={() => setSelected(item.id)} title={item.id}>
                  {item.label}{!item.anchorable && " (context)"}{item.deprecated && " (deprecated)"}
                </button>
              </div>;
            })}
          </div>
        </div>
      </div>
      {rows.length === 0 && <p>No terms match this search.</p>}
      {term && <div className="taxonomy-detail" aria-label="selected ontology term">
        <h3>{term.label}</h3><code>{term.id}</code>
        <p>{term.definition ?? "No definition provided."}</p>
        {term.synonyms.length > 0 && <p>Also named: {term.synonyms.join(", ")}</p>}
        {term.parents.length > 0 && <div>Parents: {term.parents.map((id) => <button type="button" key={id}
          onClick={() => inspect(id)}>{index.byId.get(id)?.label ?? id}</button>)}</div>}
        {(index.children.get(term.id)?.length ?? 0) > 0 && <details><summary>Children</summary>
          {index.children.get(term.id)?.map((id) => <button type="button" key={id}
            onClick={() => inspect(id)}>{index.byId.get(id)?.label ?? id}</button>)}
        </details>}
        {term.anchorable ? <>
          {term.deprecated && <p>This term is deprecated in this ontology release.</p>}
          {(["left", "right"] as const).map((side) => <button type="button" key={side}
            disabled={saving || !panes[side].schema || !panes[side].selected}
            onClick={() => {
              const pane = panes[side];
              if (saving || !pane.schema || !pane.selected) return;
              dispatch(usePair({ subject: { schema: pane.schema, id: pane.selected },
                object: { schema: data.schema, id: term.id } }));
              document.getElementById("crosswalk-authoring")?.scrollIntoView?.({ block: "nearest" });
            }}>Anchor {side} selection</button>)}
          <p className="subtle">Opens a draft below. Save explicitly to add this anchor.</p>
        </> : <p>Imported ancestor shown for context. Select a PMDco term to create an anchor.</p>}
      </div>}
      {data.attribution && <details className="taxonomy-attribution"><summary>Source and license</summary>
        <p>{data.attribution}</p><p>{data.license}</p>
        <a href={data.release_url} target="_blank" rel="noreferrer">Release source</a>{" · "}
        <a href={data.license_url} target="_blank" rel="noreferrer">License</a>
      </details>}
    </>}
  </aside>;
}
