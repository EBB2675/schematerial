import { useCallback, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import { sideLabel, type Side } from "../panes";
import { useAppDispatch, useAppSelector } from "../store";
import type { SchemaSummary } from "../types";
import { activate, setDetail } from "../uiSlice";

import { ElementBrowser } from "./ElementBrowser";
import { ElementDetailPanel } from "./ElementDetailPanel";
import { PaneHeader } from "./PaneHeader";
import { SchemaGraph } from "./SchemaGraph";
import { UnsupportedNotice } from "./UnsupportedNotice";

// How much of the column the list or the graph takes, as a percentage. The list
// keeps the larger share: browsing is what the pane is for, and the detail below
// it stays legible in a strip. The graph starts with more, because a canvas
// needs room before it reads as one.
const LIST_SPLIT = 65;
const GRAPH_SPLIT = 78;
const MIN_SPLIT = 20;
const MAX_SPLIT = 92;

/**
 * One side of the aligner: its schema, its list or graph, and its detail.
 *
 * Each side inspects its own selection rather than sharing one detail region,
 * so both sides' provenance can be read at the same time -- which is the point
 * of putting two schemas next to each other. The detail region collapses to a
 * single line when the reading is about finding an element rather than
 * inspecting one, and how the remaining height divides is the reader's to set.
 */
export function SchemaPane({ side, schemas }: { side: Side; schemas: SchemaSummary[] }) {
  const dispatch = useAppDispatch();
  const pane = useAppSelector((state) => state.ui.panes[side]);
  const isActive = useAppSelector((state) => state.ui.active === side);
  const current = schemas.find((schema) => schema.name === pane.schema) ?? null;

  const stack = useRef<HTMLDivElement>(null);
  // Held here rather than in the store: a drag would otherwise dispatch on
  // every pointer move, and nothing outside this side needs to know.
  const [split, setSplit] = useState<number | null>(null);
  const effective = split ?? (pane.view === "graph" ? GRAPH_SPLIT : LIST_SPLIT);

  const clamp = useCallback(
    (value: number) => Math.min(MAX_SPLIT, Math.max(MIN_SPLIT, value)),
    [],
  );

  const drag = useCallback(
    (event: PointerEvent<HTMLDivElement>) => {
      const node = stack.current;
      if (node === null) return;
      event.preventDefault();
      const bounds = node.getBoundingClientRect();
      const onMove = (moved: globalThis.PointerEvent) => {
        if (bounds.height <= 0) return;
        setSplit(clamp(((moved.clientY - bounds.top) / bounds.height) * 100));
      };
      const onUp = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    },
    [clamp],
  );

  // The divider is reachable without a pointer, so a keyboard user can give the
  // graph the room a drag would have given it.
  const onSplitKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowUp") setSplit(clamp(effective - 5));
    else if (event.key === "ArrowDown") setSplit(clamp(effective + 5));
    else if (event.key === "Home") setSplit(MIN_SPLIT);
    else if (event.key === "End") setSplit(MAX_SPLIT);
    else return;
    event.preventDefault();
  };

  return (
    <section
      className={`pane-column ${side}${isActive ? " active" : ""}${
        current === null ? " closed" : ""
      }`}
      aria-label={`${sideLabel(side)} side`}
      onFocusCapture={() => {
        if (!isActive) dispatch(activate(side));
      }}
    >
      <PaneHeader side={side} schemas={schemas} current={current} active={isActive} />
      {current === null ? (
        <div className="pane-closed">
          <p className="subtle">Closed. Choose a schema above to compare it with the other side.</p>
        </div>
      ) : current.status === "ok" ? (
        <div className="stack" ref={stack}>
          <div
            className="region"
            style={
              pane.detail && pane.selected !== null
                ? { flexBasis: `${effective}%` }
                : { flex: "1 1 auto" }
            }
          >
            {pane.view === "graph" ? (
              <SchemaGraph side={side} schema={current.name} />
            ) : (
              <ElementBrowser side={side} schema={current.name} />
            )}
          </div>
          {pane.detail ? (
            <>
              <div
                className="splitter"
                role="separator"
                tabIndex={0}
                aria-label={`resize the ${sideLabel(side)} side`}
                aria-valuenow={Math.round(effective)}
                aria-valuemin={MIN_SPLIT}
                aria-valuemax={MAX_SPLIT}
                title="Drag to resize, double-click to reset"
                onPointerDown={drag}
                onKeyDown={onSplitKey}
                onDoubleClick={() => setSplit(null)}
              />
              {/* An empty detail region would be a third of the pane spent on one
                  sentence. Until something is selected it is only that sentence,
                  and the list has the rest. */}
              <div
                className="detail-region"
                style={
                  pane.selected === null
                    ? { flex: "0 0 auto" }
                    : { flexBasis: `${100 - effective}%` }
                }
              >
                <ElementDetailPanel side={side} schema={current.name} />
              </div>
            </>
          ) : (
            <button
              type="button"
              className="detail-collapsed"
              aria-label={`show the ${sideLabel(side)} element detail`}
              onClick={() => dispatch(setDetail({ side, open: true }))}
            >
              <span className="subtle">
                {pane.selected === null ? "No element selected" : pane.selected}
              </span>
              <span className="subtle">show detail</span>
            </button>
          )}
        </div>
      ) : (
        <UnsupportedNotice summary={current} />
      )}
    </section>
  );
}
