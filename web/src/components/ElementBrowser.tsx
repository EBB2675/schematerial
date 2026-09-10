import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { useElementsQuery, useMappingsQuery } from "../api";
import { rangeLabel } from "../format";
import { mappingStates, type MappingState } from "../mappings";
import { sideLabel, type Side } from "../panes";
import { buildHaystacks, filterElements } from "../search";
import { useAppDispatch, useAppSelector } from "../store";
import type { IndexRow } from "../types";
import {
  activate,
  filtersOf,
  selectElement,
  setKind,
  setOnlyDiagnostics,
  setOnlyInherited,
  setQuery,
} from "../uiSlice";
import { scrollToIndex, visibleRange } from "../virtual";

import { FilterControls } from "./FilterControls";

const ROW_HEIGHT = 30;
const NO_ROWS: IndexRow[] = [];

const number = new Intl.NumberFormat("en");

/**
 * One element, named the way a person names it.
 *
 * The readable name leads and gets the width. The type, the unit and the
 * conversion notes are chips at the end because they answer a second question,
 * and the stable identifier is not here at all: it is in the detail below,
 * where it can be read in full and copied without a row having to be wide
 * enough to hold it.
 */
function Row({
  row,
  selected,
  mappingState,
  onSelect,
}: {
  row: IndexRow;
  selected: boolean;
  mappingState: MappingState | undefined;
  onSelect: (id: string) => void;
}) {
  return (
    <div
      className={`row ${row.kind}${selected ? " selected" : ""}`}
      role="option"
      aria-selected={selected}
      title={row.id}
      style={{ height: ROW_HEIGHT }}
      onMouseDown={() => onSelect(row.id)}
    >
      <span className={`badge kind-${row.kind}`} aria-hidden="true">
        {row.kind === "class" ? "C" : "a"}
      </span>
      <span className="row-name">{row.name}</span>
      {row.kind === "attribute" && <span className="row-owner">{row.class_name}</span>}
      <span className="row-tail">
        {mappingState !== undefined && (
          <span className={`state ${mappingState}`} title={`In the crosswalk: ${mappingState}`}>
            {mappingState}
          </span>
        )}
        {row.range !== null && (
          <span className="chip range" title={row.range}>
            {rangeLabel(row.range)}
          </span>
        )}
        {row.unit !== null && <span className="chip unit">{row.unit}</span>}
        {row.multivalued && <span className="chip">many</span>}
        {row.inherited && (
          <span className="chip inherited" title="declared on an ancestor">
            inherited
          </span>
        )}
        {row.diagnostics > 0 && (
          <span className="chip warn" title="conversion diagnostics">
            {row.diagnostics}
          </span>
        )}
      </span>
    </div>
  );
}

/**
 * Browse and search one side's schema.
 *
 * The whole index is already in memory, so filtering is local and immediate,
 * and a second pane costs a second index fetch rather than a request per
 * keystroke. Only the rows inside the viewport are rendered, and scrolling
 * neither refilters nor rebuilds the searchable text: the work in a frame is
 * bounded by the viewport, not by how many elements the schema has.
 */
export function ElementBrowser({ side, schema, version }: { side: Side; schema: string; version: string | null }) {
  const dispatch = useAppDispatch();
  const filters = useAppSelector((state) => filtersOf(state.ui, side));
  const linked = useAppSelector((state) => state.ui.panes[side].linked);
  const selected = useAppSelector((state) => state.ui.panes[side].selected);
  const isActive = useAppSelector((state) => state.ui.active === side);
  const focusRequests = useAppSelector((state) => state.ui.focusRequests);

  const { data, isLoading, isError } = useElementsQuery(schema);
  const { data: mappings } = useMappingsQuery();
  const states = useMemo(() => mappingStates(mappings?.rows ?? [], version), [mappings, version]);
  const rows = data?.elements ?? NO_ROWS;
  const haystacks = useMemo(() => buildHaystacks(rows), [rows]);
  const filtered = useMemo(
    () => filterElements(rows, filters, haystacks),
    [rows, haystacks, filters],
  );

  const viewport = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [height, setHeight] = useState(0);

  useEffect(() => {
    const node = viewport.current;
    if (node === null) return;
    setHeight(node.clientHeight);
    const observer = new ResizeObserver(() => setHeight(node.clientHeight));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  // Handing a side the keyboard puts the caret in its list. Focus that arrived
  // by click or Tab only marks the side active, so clicking into that side's
  // own search box is not answered by throwing focus into the list.
  const lastRequest = useRef(focusRequests);
  useEffect(() => {
    if (lastRequest.current === focusRequests) return;
    lastRequest.current = focusRequests;
    if (isActive) viewport.current?.focus();
  }, [focusRequests, isActive]);

  const move = useCallback(
    (delta: number) => {
      if (filtered.length === 0) return;
      const current = filtered.findIndex((row) => row.id === selected);
      const base = current < 0 ? (delta > 0 ? -1 : 0) : current;
      const next = Math.min(Math.max(base + delta, 0), filtered.length - 1);
      const row = filtered[next];
      if (row === undefined) return;
      dispatch(selectElement({ side, id: row.id }));
      const node = viewport.current;
      if (node !== null) {
        const target = scrollToIndex(next, node.scrollTop, node.clientHeight, ROW_HEIGHT);
        if (target !== null) node.scrollTop = target;
      }
    },
    [filtered, selected, dispatch, side],
  );

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const page = Math.max(1, Math.floor(height / ROW_HEIGHT) - 1);
    switch (event.key) {
      case "ArrowDown":
        move(1);
        break;
      case "ArrowUp":
        move(-1);
        break;
      case "PageDown":
        move(page);
        break;
      case "PageUp":
        move(-page);
        break;
      case "Home":
        move(-filtered.length);
        break;
      case "End":
        move(filtered.length);
        break;
      default:
        return;
    }
    event.preventDefault();
  };

  const windowed = visibleRange(scrollTop, height, ROW_HEIGHT, filtered.length);
  const where = sideLabel(side);
  const empty = !isLoading && !isError && filtered.length === 0;

  return (
    <div className="browser">
      {!linked && (
        <FilterControls
          side={side}
          filters={filters}
          label={`search the ${where} side`}
          placeholder={`search the ${where} side`}
          onQuery={(value) => dispatch(setQuery({ side, value }))}
          onKind={(value) => dispatch(setKind({ side, value }))}
          onInherited={(value) => dispatch(setOnlyInherited({ side, value }))}
          onDiagnostics={(value) => dispatch(setOnlyDiagnostics({ side, value }))}
          onArrowDown={() => {
            viewport.current?.focus();
            move(1);
          }}
        />
      )}
      <p className="count-line subtle">
        {isLoading && "loading the element index…"}
        {isError && "the element index could not be loaded"}
        {!isLoading &&
          !isError &&
          `${number.format(filtered.length)} of ${number.format(rows.length)} elements`}
        {!linked && !isLoading && !isError && " · own search"}
      </p>
      <div
        className="viewport"
        ref={viewport}
        tabIndex={0}
        role="listbox"
        aria-label={`elements of ${schema} on the ${where}`}
        onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
        onKeyDown={onKeyDown}
      >
        <div className="spacer" style={{ height: windowed.total }}>
          <div className="slice" style={{ transform: `translateY(${windowed.offset}px)` }}>
            {filtered.slice(windowed.start, windowed.end).map((row) => (
              <Row
                key={row.id}
                row={row}
                selected={row.id === selected}
                mappingState={states.get(row.id)}
                onSelect={(id) => {
                  dispatch(activate(side));
                  dispatch(selectElement({ side, id }));
                }}
              />
            ))}
          </div>
        </div>
      </div>
      {empty && (
        <p className="empty-state">
          {rows.length === 0
            ? "This schema has no browsable elements."
            : "Nothing matches this search."}
        </p>
      )}
    </div>
  );
}
