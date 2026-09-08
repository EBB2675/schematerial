import { skipToken } from "@reduxjs/toolkit/query/react";
import { useMemo } from "react";

import { useElementsQuery } from "../api";
import { usePair } from "../authoringSlice";
import { elementLabel, idPrefix } from "../format";
import { otherSide, sideLabel, type Side } from "../panes";
import { useAppDispatch, useAppSelector } from "../store";
import type { IndexRow } from "../types";
import { setAuthoring, setPmdco, swapPair } from "../uiSlice";

import { Copyable } from "./Copyable";

interface Chosen {
  side: Side;
  schema: string | null;
  id: string | null;
  row: IndexRow | undefined;
}

/**
 * The element each side has selected, and the one action that turns the pair
 * into a draft.
 *
 * Reading the strip asserts nothing: it says what a person is comparing right
 * now. Nothing here proposes, scores or records a correspondence. The arrow is
 * the direction a mapping would be written in, and it can be turned round before
 * the form is ever opened, so subject and object are a decision rather than a
 * consequence of which pane a schema happened to land in.
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

function End({ chosen, role }: { chosen: Chosen; role: "subject" | "object" }) {
  return (
    <div className="strip-end">
      <span className="strip-role">{role}</span>
      {chosen.id === null ? (
        <span className="subtle strip-empty">
          {chosen.schema === null
            ? `${sideLabel(chosen.side)} side closed`
            : `nothing selected on the ${sideLabel(chosen.side)}`}
        </span>
      ) : (
        <>
          {chosen.row !== undefined && (
            <span className={`badge kind-${chosen.row.kind}`} aria-hidden="true">
              {chosen.row.kind === "class" ? "C" : "a"}
            </span>
          )}
          <span className="strip-name" title={chosen.id}>
            {chosen.row === undefined ? chosen.id : elementLabel(chosen.row)}
          </span>
          <span className="chip source">{idPrefix(chosen.id)}</span>
          <code className="strip-id">{chosen.id}</code>
          <Copyable value={chosen.id} label={`the ${sideLabel(chosen.side)} identifier`} />
        </>
      )}
    </div>
  );
}

/**
 * `subject` is whichever side the arrow points away from. A mapping is
 * directional, so this is a real choice and not a presentation detail.
 */
export function SelectionStrip() {
  const dispatch = useAppDispatch();
  const left = useChosen("left");
  const right = useChosen("right");
  const direction = useAppSelector((state) => state.ui.direction);
  const chosen: Record<Side, Chosen> = { left, right };
  const subjectSide: Side = direction === "lr" ? "left" : "right";
  const subject = chosen[subjectSide];
  const object = chosen[otherSide(subjectSide)];
  const both = subject.id !== null && object.id !== null;

  function startDraft() {
    if (subject.schema === null || subject.id === null) return;
    if (object.schema === null || object.id === null) return;
    dispatch(
      usePair({
        subject: { schema: subject.schema, id: subject.id },
        object: { schema: object.schema, id: object.id },
      }),
    );
    dispatch(setAuthoring(true));
  }

  return (
    <footer className="strip" aria-label="selected on each side">
      <End chosen={subject} role="subject" />
      <span className="strip-arrow" aria-hidden="true">
        →
      </span>
      <End chosen={object} role="object" />
      <div className="strip-actions">
        <button
          type="button"
          className="btn"
          aria-label="swap subject and object"
          title="Swap which side is the subject"
          onClick={() => dispatch(swapPair())}
        >
          swap
        </button>
        <button type="button" className="btn primary" disabled={!both} onClick={startDraft}>
          Create mapping
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => dispatch(setPmdco(true))}
          title="Open PMDco and anchor the selected element to a term"
        >
          Add semantic anchor
        </button>
      </div>
    </footer>
  );
}
