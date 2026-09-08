import { useEffect, useMemo, useRef, useState } from "react";

import { usePmdcoQuery } from "../api";
import { usePair } from "../authoringSlice";
import { useAppDispatch, useAppSelector } from "../store";
import { ancestorIds, buildTaxonomy, outline, searchTaxonomy } from "../taxonomy";
import type { TaxonomyTerm } from "../types";
import { setAuthoring, setPmdco } from "../uiSlice";
import { visibleRange } from "../virtual";

const EMPTY: TaxonomyTerm[] = [];
const ROW_HEIGHT = 28;

/**
 * PMDco as a third thing to point at, not a third pane competing for the window.
 *
 * The taxonomy is a dock that stays closed until someone asks for a semantic
 * anchor. It is a tree, never boxes with slot lists, and everything in it comes
 * from a bundled release: no lookup service, no inference, no network beyond the
 * server that is already serving the schemas.
 *
 * An anchor is an additional row. It never replaces the direct NOMAD–BAM
 * mapping between the two elements, and saving it is the same explicit human
 * action as saving any other row.
 */
export function PmdcoPanel() {
  const dispatch = useAppDispatch();
  const open = useAppSelector((state) => state.ui.pmdco);
  const panes = useAppSelector((state) => state.ui.panes);
  const saving = useAppSelector((state) => state.authoring.saving);
  // Fetched the first time the dock is opened, then kept for the session.
  const { data, isLoading, isError, refetch } = usePmdcoQuery(undefined, { skip: !open });

  const index = useMemo(() => buildTaxonomy(data?.terms ?? EMPTY), [data]);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const [scroll, setScroll] = useState(0);
  const [height, setHeight] = useState(280);
  const viewport = useRef<HTMLDivElement>(null);

  const searching = query.trim() !== "";
  const rows = useMemo(
    () =>
      searching
        ? searchTaxonomy(index, query).map((term) => ({ term, depth: 0 }))
        : outline(index, expanded),
    [index, query, searching, expanded],
  );
  const term = selected === null ? undefined : index.byId.get(selected);
  const windowed = visibleRange(scroll, height, ROW_HEIGHT, rows.length);

  useEffect(() => {
    const node = viewport.current;
    if (node === null) return;
    const measure = () => setHeight(node.clientHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [data, open]);

  useEffect(() => {
    const position = rows.findIndex((row) => row.term.id === selected);
    const node = viewport.current;
    if (position < 0 || node === null) return;
    const top = position * ROW_HEIGHT;
    if (top < node.scrollTop || top + ROW_HEIGHT > node.scrollTop + node.clientHeight) {
      node.scrollTop = top;
      setScroll(top);
    }
  }, [selected, rows]);

  function inspect(id: string) {
    setSelected(id);
    setQuery("");
    setExpanded((current) => new Set([...current, ...ancestorIds(index, id)]));
  }

  function toggle(id: string) {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (!open) return null;

  return (
    <aside className="pmdco" aria-label="PMDco taxonomy">
      <header className="pmdco-head">
        <h2>PMDco{data === undefined ? "" : ` ${data.version}`}</h2>
        <button
          type="button"
          className="btn"
          aria-label="close the PMDco panel"
          onClick={() => dispatch(setPmdco(false))}
        >
          close
        </button>
      </header>

      {isLoading && <p className="subtle">Loading the offline taxonomy…</p>}
      {isError && (
        <p className="alert" role="alert">
          PMDco could not be loaded.{" "}
          <button type="button" className="btn" onClick={() => void refetch()}>
            Retry taxonomy
          </button>
        </p>
      )}

      {data !== undefined && (
        <>
          <input
            type="search"
            className="search pmdco-search"
            value={query}
            aria-label="Search PMDco"
            placeholder="search terms, synonyms and definitions"
            onChange={(event) => {
              setQuery(event.target.value);
              setScroll(0);
              if (viewport.current !== null) viewport.current.scrollTop = 0;
            }}
          />
          <p className="count-line subtle">
            {rows.length} {searching ? "results" : "visible"} · {data.anchor_count} anchorable terms
            · offline
          </p>

          <div
            className="taxonomy"
            ref={viewport}
            role="tree"
            aria-label="ontology terms"
            tabIndex={0}
            onScroll={(event) => setScroll(event.currentTarget.scrollTop)}
            onKeyDown={(event) => {
              if (event.target !== event.currentTarget) return;
              const current = rows.findIndex((row) => row.term.id === selected);
              if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                const next = Math.max(
                  0,
                  Math.min(rows.length - 1, current + (event.key === "ArrowDown" ? 1 : -1)),
                );
                setSelected(rows[next]?.term.id ?? null);
              } else if (event.key === "ArrowRight" && selected !== null && !expanded.has(selected)) {
                event.preventDefault();
                toggle(selected);
              } else if (event.key === "ArrowLeft" && selected !== null && expanded.has(selected)) {
                event.preventDefault();
                toggle(selected);
              }
            }}
          >
            <div className="spacer" style={{ height: windowed.total }}>
              <div className="slice" style={{ transform: `translateY(${windowed.offset}px)` }}>
                {rows.slice(windowed.start, windowed.end).map(({ term: item, depth }) => {
                  const hasChildren = (index.children.get(item.id)?.length ?? 0) > 0;
                  return (
                    <div
                      key={item.id}
                      role="treeitem"
                      aria-level={depth + 1}
                      aria-selected={selected === item.id}
                      aria-expanded={
                        hasChildren && !searching ? expanded.has(item.id) : undefined
                      }
                      className={`taxonomy-row${selected === item.id ? " selected" : ""}`}
                      style={{ height: ROW_HEIGHT, paddingLeft: Math.min(depth, 10) * 12 }}
                    >
                      {hasChildren && !searching ? (
                        <button
                          type="button"
                          className="twisty"
                          aria-label={`${expanded.has(item.id) ? "Collapse" : "Expand"} ${item.label}`}
                          onClick={() => toggle(item.id)}
                        >
                          {expanded.has(item.id) ? "−" : "+"}
                        </button>
                      ) : (
                        <span className="twisty" aria-hidden="true" />
                      )}
                      <button
                        type="button"
                        className="taxonomy-name"
                        onClick={() => setSelected(item.id)}
                        title={item.id}
                      >
                        {item.label}
                        {!item.anchorable && " (context)"}
                        {item.deprecated && " (deprecated)"}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          {rows.length === 0 && <p className="empty-state">No terms match this search.</p>}

          {term !== undefined && (
            <div className="taxonomy-detail" aria-label="selected ontology term">
              <h3>{term.label}</h3>
              <code className="identifier">{term.id}</code>
              <p>{term.definition ?? "No definition provided."}</p>
              {term.synonyms.length > 0 && <p className="subtle">Also named: {term.synonyms.join(", ")}</p>}
              {term.parents.length > 0 && (
                <p className="term-links">
                  <span className="field-label">parents</span>
                  {term.parents.map((id) => (
                    <button type="button" className="link" key={id} onClick={() => inspect(id)}>
                      {index.byId.get(id)?.label ?? id}
                    </button>
                  ))}
                </p>
              )}
              {(index.children.get(term.id)?.length ?? 0) > 0 && (
                <details className="disclosure inline">
                  <summary>Children</summary>
                  <div className="term-links">
                    {index.children.get(term.id)?.map((id) => (
                      <button type="button" className="link" key={id} onClick={() => inspect(id)}>
                        {index.byId.get(id)?.label ?? id}
                      </button>
                    ))}
                  </div>
                </details>
              )}
              {term.anchorable ? (
                <div className="anchor-actions">
                  {term.deprecated && (
                    <p className="subtle">This term is deprecated in this ontology release.</p>
                  )}
                  {(["left", "right"] as const).map((side) => (
                    <button
                      type="button"
                      className="btn primary"
                      key={side}
                      disabled={saving || panes[side].schema === null || panes[side].selected === null}
                      onClick={() => {
                        const pane = panes[side];
                        if (saving || pane.schema === null || pane.selected === null) return;
                        dispatch(
                          usePair({
                            subject: { schema: pane.schema, id: pane.selected },
                            object: { schema: data.schema, id: term.id },
                          }),
                        );
                        dispatch(setAuthoring(true));
                      }}
                    >
                      Anchor {side} selection
                    </button>
                  ))}
                  <p className="subtle">
                    Opens a draft. Saving it adds an anchor row alongside any direct mapping.
                  </p>
                </div>
              ) : (
                <p className="subtle">
                  Imported ancestor shown for context. Select a PMDco term to create an anchor.
                </p>
              )}
            </div>
          )}

          {data.attribution !== undefined && (
            <details className="disclosure inline attribution">
              <summary>Source and license</summary>
              <div>
                <p>{data.attribution}</p>
                <p>{data.license}</p>
                <a href={data.release_url} target="_blank" rel="noreferrer">
                  Release source
                </a>
                {" · "}
                <a href={data.license_url} target="_blank" rel="noreferrer">
                  License
                </a>
              </div>
            </details>
          )}
        </>
      )}
    </aside>
  );
}
