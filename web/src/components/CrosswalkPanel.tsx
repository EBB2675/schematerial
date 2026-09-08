import { useEffect, useState, type FormEvent } from "react";

import { useHumanWriteMutation, useMappingsQuery, useReviewSessionMutation } from "../api";
import { clearDraft, editDraft, reviewRow, setSaving, swapDirection, usePair } from "../authoringSlice";
import { useAppDispatch, useAppSelector } from "../store";

function failure(error: unknown): string {
  if (typeof error === "object" && error !== null && "data" in error) {
    const data = error.data as { detail?: unknown };
    if (typeof data?.detail === "string") return data.detail;
  }
  return "The server could not save this change. Your draft is still unsaved.";
}

export function CrosswalkPanel() {
  const dispatch = useAppDispatch();
  const draft = useAppSelector((state) => state.authoring);
  const panes = useAppSelector((state) => state.ui.panes);
  const { data, isError, refetch } = useMappingsQuery();
  const [session, sessionState] = useReviewSessionMutation();
  const [write, writeState] = useHumanWriteMutation();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const busy = sessionState.isLoading || writeState.isLoading || draft.saving;
  const paired = panes.left.schema && panes.left.selected && panes.right.schema && panes.right.selected;
  const ready = draft.subject && draft.object && draft.author.trim() && draft.comment.trim()
    && draft.confidence !== "" && Number(draft.confidence) >= 0 && Number(draft.confidence) <= 1;

  useEffect(() => {
    if (!draft.dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [draft.dirty]);

  async function save(action?: "accept" | "reject") {
    if (!ready || busy || !draft.subject || !draft.object) return;
    setError(""); setMessage("");
    dispatch(setSaving(true));
    try {
      const { token } = await session().unwrap();
      const payload = draft.reviewId ? {
        record_id: draft.reviewId, action, author_id: draft.author, comment: draft.comment,
      } : {
        subject_schema: draft.subject.schema, subject_id: draft.subject.id,
        object_schema: draft.object.schema, object_id: draft.object.id,
        predicate_id: draft.predicate, author_id: draft.author, comment: draft.comment,
        confidence: Number(draft.confidence),
      };
      await write({ route: draft.reviewId ? "review" : "mappings", token, payload }).unwrap();
      dispatch(clearDraft());
      setMessage("Saved to the crosswalk.");
    } catch (caught) { setError(failure(caught)); }
    finally { dispatch(setSaving(false)); }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    // A review requires the explicit Accept or Reject button, never Enter in a field.
    if (!draft.reviewId) void save();
  }

  return <section id="crosswalk-authoring" className="crosswalk" aria-label="crosswalk authoring and review">
    <div className="crosswalk-heading">
      <h2>Crosswalk</h2>
      <span role="status">{busy ? "Saving…" : draft.dirty ? "Unsaved changes" : message || "No unsaved changes"}</span>
      <button type="button" onClick={() => void refetch()}>Reload mappings</button>
    </div>
    {isError && <p role="alert">Mappings could not be loaded. Start the server with mapping storage enabled.</p>}
    {error && <p role="alert">{error}</p>}
    <form onSubmit={submit}>
      <fieldset disabled={busy}>
        <legend>{draft.reviewId ? "Review suggestion" : "Create a mapping"}</legend>
        <div className="mapping-controls">
          <button type="button" disabled={!paired} onClick={() => {
            if (!panes.left.schema || !panes.left.selected || !panes.right.schema || !panes.right.selected) return;
            dispatch(usePair({ subject: { schema: panes.left.schema, id: panes.left.selected },
              object: { schema: panes.right.schema, id: panes.right.selected } }));
            setError(""); setMessage("");
          }}>Use selected pair</button>
          <button type="button" disabled={!draft.subject || !draft.object || !!draft.reviewId}
            onClick={() => dispatch(swapDirection())}>Reverse direction</button>
          <button type="button" disabled={!draft.dirty} onClick={() => {
            dispatch(clearDraft()); setError(""); setMessage("");
          }}>Discard draft</button>
        </div>
        <p className="mapping-direction" aria-label="mapping direction">
          Subject: <code>{draft.subject?.id ?? "choose a pair"}</code>
          {" → "}<strong>{draft.predicate.replace("skos:", "")}</strong>{" → "}
          Object: <code>{draft.object?.id ?? "choose a pair"}</code>
        </p>
        <div className="mapping-fields">
          <label>Predicate<select value={draft.predicate} disabled={!!draft.reviewId}
            onChange={(e) => dispatch(editDraft({ predicate: e.target.value }))}>
            {["exact", "close", "related", "narrow", "broad"].map((name) =>
              <option key={name} value={`skos:${name}Match`}>{name}</option>)}
          </select></label>
          <label>Author URI or ORCID<input required value={draft.author}
            placeholder="https://orcid.org/…" onChange={(e) => dispatch(editDraft({ author: e.target.value }))} /></label>
          {!draft.reviewId && <label>Confidence<input type="number" min="0" max="1" step="any" required
            value={draft.confidence} onChange={(e) => dispatch(editDraft({ confidence: e.target.value }))} /></label>}
          <label className="justification">Justification<textarea required value={draft.comment}
            onChange={(e) => dispatch(editDraft({ comment: e.target.value }))} /></label>
        </div>
        {draft.predicate === "skos:narrowMatch" && <p>Subject has a narrower matching object.</p>}
        {draft.predicate === "skos:broadMatch" && <p>Subject has a broader matching object.</p>}
        {draft.reviewId ? <div className="mapping-controls">
          <button type="button" disabled={!ready} onClick={() => void save("accept")}>Accept suggestion</button>
          <button type="button" disabled={!ready} onClick={() => void save("reject")}>Reject suggestion</button>
        </div> : <button type="submit" disabled={!ready}>Save accepted mapping</button>}
      </fieldset>
    </form>
    <ul className="mapping-records" aria-label="saved mappings">
      {(data?.rows ?? []).map((row) => <li key={row.record_id}>
        <span className={`mapping-state ${row.review_status}`}>{row.review_status}</span>{" "}
        <code>{row.subject_id}</code>{" → "}<strong>{row.predicate_id.replace("skos:", "")}</strong>{" → "}
        <code>{row.object_id}</code>
        <p>{row.author_id} · {row.mapping_date} · confidence {row.confidence}</p>
        <p className="mapping-comment">{row.comment}</p>
        {row.review_status === "suggested" && <button type="button" disabled={busy}
          onClick={() => { dispatch(reviewRow({ id: row.record_id, subject: row.subject_id,
            object: row.object_id, predicate: row.predicate_id })); setError(""); setMessage(""); }}>
          Review suggestion
        </button>}
      </li>)}
    </ul>
  </section>;
}
