import { useCallback, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import { sideLabel, type Side } from "../panes";
import { useAppDispatch, useAppSelector } from "../store";
import type { SchemaSummary } from "../types";
import { activate } from "../uiSlice";

import { ElementBrowser } from "./ElementBrowser";
import { ElementDetailPanel } from "./ElementDetailPanel";
import { SchemaGraph } from "./SchemaGraph";
import { SchemaHeader } from "./SchemaHeader";
import { UnsupportedNotice } from "./UnsupportedNotice";

// How much of the column the list or the graph takes, as a percentage. The
// graph starts with more of it: a canvas needs room before it reads as one,
// while a detail panel stays legible in a strip.
const LIST_SPLIT = 55;
const GRAPH_SPLIT = 74;
const MIN_SPLIT = 20;
const MAX_SPLIT = 92;

/**
 * One side of the aligner: its schema picker, its list or graph, and its detail.
 *
 * Each side inspects its own selection rather than sharing one detail region,
 * so both sides' provenance can be read at the same time -- which is the point
 * of putting two schemas next to each other. How the height divides between the
 * two is the reader's to set, because a graph and a list want different amounts
 * of it.
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
      <SchemaHeader side={side} schemas={schemas} current={current} active={isActive} />
      {current === null ? (
        <div className="pane-closed">
          <p className="subtle">
            This side is closed. Choose a schema above to compare it with the other side.
          </p>
        </div>
      ) : current.status === "ok" ? (
        <div className="stack" ref={stack}>
          <div className="region" style={{ flexBasis: `${effective}%` }}>
            {pane.view === "graph" ? (
              <SchemaGraph side={side} schema={current.name} />
            ) : (
              <ElementBrowser side={side} schema={current.name} />
            )}
          </div>
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
          <div className="detail-region" style={{ flexBasis: `${100 - effective}%` }}>
            <ElementDetailPanel side={side} schema={current.name} />
          </div>
        </div>
      ) : (
        <UnsupportedNotice summary={current} />
      )}
    </section>
  );
}
