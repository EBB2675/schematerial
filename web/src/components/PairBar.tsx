import { skipToken } from "@reduxjs/toolkit/query/react";
import { useMemo } from "react";

import { useElementsQuery } from "../api";
import { sideLabel, SIDES, type Side } from "../panes";
import { useAppSelector } from "../store";
import type { IndexRow } from "../types";

interface Chosen {
  side: Side;
  schema: string | null;
  id: string | null;
  row: IndexRow | undefined;
}

/**
 * The element each side has selected, shown together.
 *
 * This is a reading of the current state, not an assertion about it: the two
 * identifiers are what a person is comparing right now. Nothing here proposes,
 * scores or records a correspondence between them. The separate authoring form
 * copies this selection only when the human chooses Use selected pair.
 */
function useChosen(side: Side): Chosen {
  const pane = useAppSelector((state) => state.ui.panes[side]);
  const { data } = useElementsQuery(pane.schema ?? skipToken);
  const rows = data?.elements;
  const row = useMemo(
    () => (pane.selected === null ? undefined : rows?.find((r) => r.id === pane.selected)),
    [rows, pane.selected],
  );
  return { side, schema: pane.schema, id: pane.selected, row };
}

function Chosen({ chosen }: { chosen: Chosen }) {
  return (
    <div className="pair-side">
      <span className="pair-label">{sideLabel(chosen.side)}</span>
      {chosen.id === null ? (
        <span className="subtle">
          {chosen.schema === null ? "closed" : "nothing selected"}
        </span>
      ) : (
        <>
          {chosen.row !== undefined && (
            <>
              <span className={`badge kind-${chosen.row.kind}`}>
                {chosen.row.kind === "class" ? "C" : "a"}
              </span>
              <span className="pair-name">
                {chosen.row.kind === "attribute"
                  ? `${chosen.row.class_name}.${chosen.row.name}`
                  : chosen.row.name}
              </span>
            </>
          )}
          <code className="pair-id">{chosen.id}</code>
        </>
      )}
    </div>
  );
}

export function PairBar() {
  const left = useChosen("left");
  const right = useChosen("right");
  const chosen: Record<Side, Chosen> = { left, right };
  const both = left.id !== null && right.id !== null;
  return (
    <footer className="pair-bar" aria-label="selected on each side">
      {SIDES.map((side) => (
        <Chosen key={side} chosen={chosen[side]} />
      ))}
      <p className="subtle pair-note">
        {both
          ? "Choose Use selected pair to start a mapping draft."
          : "Select an element on each side to see both identifiers here."}
      </p>
    </footer>
  );
}
