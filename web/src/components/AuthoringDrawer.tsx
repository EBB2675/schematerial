import { skipToken } from "@reduxjs/toolkit/query/react";
import { useEffect, useRef, type FormEvent } from "react";

import { useCatalogueQuery, useElementsQuery, useHumanWriteMutation, useMappingsQuery, usePmdcoQuery, useReviewSessionMutation } from "../api";
import {
  clearDraft,
  editDraft,
  failed,
  isComplete,
  saveStatus,
  saved,
  setSaving,
  swapDirection,
  usePair,
  type MappingEnd,
} from "../authoringSlice";
import { PREDICATES, elementLabel, endpointVersionLabel, idPrefix, predicateLabel, predicateSense, snapshotLabel } from "../format";
import { useAppDispatch, useAppSelector } from "../store";
import type { ElementSnapshot } from "../types";
import { setAuthoring } from "../uiSlice";

function failure(error: unknown): string {
  if (typeof error === "object" && error !== null && "data" in error) {
    const data = error.data as { detail?: unknown };
    if (typeof data?.detail === "string") return data.detail;
  }
  return "The server could not save this change. Your draft is still unsaved.";
}

/** A draft endpoint, read back as a name where the index knows one. */
function End({ end, role, snapshot }: { end: MappingEnd | null; role: string; snapshot: ElementSnapshot | undefined }) {
  const ontology = end?.schema === "pmdco";
  const { data } = useElementsQuery(end === null || end.schema === "" || ontology ? skipToken : end.schema);
  const { data: catalogue } = useCatalogueQuery();
  const { data: taxonomy } = usePmdcoQuery(ontology ? undefined : skipToken);
  const row = end === null ? undefined : data?.elements.find((entry) => entry.id === end.id);
  const version = snapshot !== undefined
    ? snapshot.source_version
    : ontology ? taxonomy?.version
    : catalogue?.schemas.find((entry) => entry.name === end?.schema)?.source.version;
  return (
    <div className="draft-end">
      <span className="draft-role">{role}</span>
      {end === null ? (
        <span className="subtle">not chosen</span>
      ) : (
        <>
          <span className="draft-name">{snapshot !== undefined ? snapshotLabel(snapshot, end.id) : row === undefined ? end.id : elementLabel(row)}</span>
          <span className="chip source">{idPrefix(end.id)}</span>
          <span className="chip">{endpointVersionLabel(version)}</span>
          <code className="draft-id">{end.id}</code>
        </>
      )}
    </div>
  );
}

/**
 * The authoring form, on demand.
 *
 * It opens over the workspace instead of living under it, because a form that is
 * always on screen spends the height that browsing needs and still has to be
 * scrolled to. Closing it hides the form and keeps the draft: the only ways a
 * draft ends are saving it or discarding it on purpose.
 *
 * Nothing here decides a review status. Creating writes a row through the human
 * route; reviewing requires the explicit Accept or Reject button, never Enter in
 * a field.
 */
export function AuthoringDrawer() {
  const dispatch = useAppDispatch();
  const draft = useAppSelector((state) => state.authoring);
  const open = useAppSelector((state) => state.ui.authoring);
  const panes = useAppSelector((state) => state.ui.panes);
  const direction = useAppSelector((state) => state.ui.direction);
  const { data } = useMappingsQuery();
  const [session, sessionState] = useReviewSessionMutation();
  const [write, writeState] = useHumanWriteMutation();
  const panel = useRef<HTMLDivElement>(null);

  const busy = sessionState.isLoading || writeState.isLoading || draft.saving;
  const ready = isComplete(draft);
  const reviewing = draft.reviewId !== null;
  const row = data?.rows.find((entry) => entry.record_id === draft.reviewId);
  const suggested = row?.review_status === "suggested";
  const subjectSide = direction === "lr" ? "left" : "right";
  const objectSide = direction === "lr" ? "right" : "left";
  const paired =
    panes[subjectSide].schema !== null &&
    panes[subjectSide].selected !== null &&
    panes[objectSide].schema !== null &&
    panes[objectSide].selected !== null;

  useEffect(() => {
    if (open) panel.current?.focus();
  }, [open]);

  async function save(action?: "accept" | "reject") {
    if (!ready || busy || draft.subject === null || draft.object === null) return;
    dispatch(setSaving(true));
    try {
      const { token } = await session().unwrap();
      const payload =
        draft.reviewId !== null
          ? {
              record_id: draft.reviewId,
              action,
              author_id: draft.author,
              comment: draft.comment,
              predicate_id: draft.predicate,
            }
          : {
              subject_schema: draft.subject.schema,
              subject_id: draft.subject.id,
              object_schema: draft.object.schema,
              object_id: draft.object.id,
              predicate_id: draft.predicate,
              author_id: draft.author,
              comment: draft.comment,
              confidence: Number(draft.confidence),
            };
      await write({
        route: draft.reviewId !== null ? "review" : "mappings",
        token,
        payload,
      }).unwrap();
      dispatch(saved("Saved to the crosswalk."));
      // There is nothing left to edit, and the panes are what the next decision
      // is made from. The report stays in the bar above them.
      dispatch(setAuthoring(false));
    } catch (caught) {
      dispatch(failed(failure(caught)));
    } finally {
      dispatch(setSaving(false));
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!reviewing) void save();
  }

  function discard() {
    // A draft is the only unsaved thing in the interface; losing one to a
    // mis-click is not recoverable, so it is confirmed.
    if (draft.dirty && !window.confirm("Discard this draft? It has not been saved.")) return;
    dispatch(clearDraft());
  }

  if (!open) return null;

  return (
    <div
      className="drawer"
      role="dialog"
      aria-label="mapping authoring"
      aria-modal="false"
      // Clicking away closes the form and keeps the draft, exactly as the close
      // button and Escape do. Nothing here can lose unsaved work.
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) dispatch(setAuthoring(false));
      }}
    >
      <div className="drawer-panel" ref={panel} tabIndex={-1}>
        <header className="drawer-head">
          <h2>{reviewing ? "Review or correct" : "Create a mapping"}</h2>
          <span className="subtle">{saveStatus(draft, busy)}</span>
          <button
            type="button"
            className="btn"
            aria-label="close the authoring drawer"
            title="Close. The draft is kept."
            onClick={() => dispatch(setAuthoring(false))}
          >
            close
          </button>
        </header>

        {draft.error !== "" && (
          <p className="alert" role="alert">
            {draft.error}
          </p>
        )}

        <form onSubmit={submit}>
          <fieldset disabled={busy}>
            <legend className="sr-only">
              {reviewing ? "Review or correct mapping" : "Create a mapping"}
            </legend>

            <div className="draft-direction" aria-label="mapping direction">
              <End end={draft.subject} role="subject" snapshot={row?.subject_snapshot} />
              <div className="draft-predicate">
                <span aria-hidden="true">↓</span>
                <strong>{predicateLabel(draft.predicate)}</strong>
                <span aria-hidden="true">↓</span>
              </div>
              <End end={draft.object} role="object" snapshot={row?.object_snapshot} />
            </div>
            <p className="subtle draft-sense">{predicateSense(draft.predicate)}</p>

            <div className="draft-controls">
              <button
                type="button"
                className="btn"
                disabled={!paired}
                onClick={() => {
                  const subject = panes[subjectSide];
                  const object = panes[objectSide];
                  if (subject.schema === null || subject.selected === null) return;
                  if (object.schema === null || object.selected === null) return;
                  dispatch(
                    usePair({
                      subject: { schema: subject.schema, id: subject.selected },
                      object: { schema: object.schema, id: object.selected },
                    }),
                  );
                }}
              >
                Use selected pair
              </button>
              <button
                type="button"
                className="btn"
                disabled={draft.subject === null || draft.object === null || reviewing}
                onClick={() => dispatch(swapDirection())}
              >
                Reverse direction
              </button>
              <button type="button" className="btn" disabled={!draft.dirty} onClick={discard}>
                Discard draft
              </button>
            </div>

            <div className="draft-fields">
              <label>
                Predicate
                <select
                  value={draft.predicate}
                  onChange={(event) => dispatch(editDraft({ predicate: event.target.value }))}
                >
                  {PREDICATES.map((name) => (
                    <option key={name} value={`skos:${name}Match`}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Author URI or ORCID
                <input
                  required
                  value={draft.author}
                  placeholder="https://orcid.org/…"
                  onChange={(event) => dispatch(editDraft({ author: event.target.value }))}
                />
              </label>
              {!reviewing && (
                <label>
                  Confidence
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="any"
                    required
                    value={draft.confidence}
                    onChange={(event) => dispatch(editDraft({ confidence: event.target.value }))}
                  />
                </label>
              )}
              <label className="justification">
                Justification
                <textarea
                  required
                  value={draft.comment}
                  onChange={(event) => dispatch(editDraft({ comment: event.target.value }))}
                />
              </label>
            </div>

            {reviewing ? (
              <div className="draft-controls">
                <button
                  type="button"
                  className="btn primary"
                  disabled={!ready}
                  onClick={() => void save("accept")}
                >
                  {suggested ? "Accept suggestion" : "Save accepted correction"}
                </button>
                <button
                  type="button"
                  className="btn danger"
                  disabled={!ready}
                  onClick={() => void save("reject")}
                >
                  {suggested ? "Reject suggestion" : "Retract mapping"}
                </button>
              </div>
            ) : (
              <div className="draft-controls">
                <button type="submit" className="btn primary" disabled={!ready}>
                  Save accepted mapping
                </button>
              </div>
            )}
            <p className="subtle">
              Saving is the human act that accepts a row. Nothing else in this interface can.
            </p>
          </fieldset>
        </form>
      </div>
    </div>
  );
}
