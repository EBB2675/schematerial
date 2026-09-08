/**
 * The mapping draft, and what happened the last time it was saved.
 *
 * The draft is the only place an unsaved correspondence exists, and it is
 * deliberately not owned by the form: the form can be closed, the workspace can
 * be switched and the panes can be browsed without the draft changing. That is
 * what makes "an unsaved state is clearly indicated" checkable from anywhere in
 * the interface rather than only while the form is on screen.
 *
 * Nothing here writes a review status. A draft becomes a record only through the
 * explicit human action the drawer offers, and the server decides the status.
 */

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

export interface MappingEnd {
  schema: string;
  id: string;
}

export interface AuthoringDraft {
  subject: MappingEnd | null;
  object: MappingEnd | null;
  predicate: string;
  author: string;
  comment: string;
  confidence: string;
  /** The record being reviewed or corrected, or null while creating a new row. */
  reviewId: string | null;
  dirty: boolean;
  saving: boolean;
  /** What the last successful save said, cleared as soon as editing resumes. */
  message: string;
  /** Why the last save failed. The draft is kept exactly as it was. */
  error: string;
}

const initialState: AuthoringDraft = {
  subject: null,
  object: null,
  predicate: "skos:closeMatch",
  author: "",
  comment: "",
  confidence: "1",
  reviewId: null,
  dirty: false,
  saving: false,
  message: "",
  error: "",
};

/** Editing again retracts whatever the last save reported. */
function editing(state: AuthoringDraft): void {
  state.dirty = true;
  state.message = "";
  state.error = "";
}

export const authoringSlice = createSlice({
  name: "authoring",
  initialState,
  reducers: {
    usePair(state, action: PayloadAction<{ subject: MappingEnd; object: MappingEnd }>) {
      if (state.saving) return;
      Object.assign(state, action.payload, { reviewId: null });
      editing(state);
    },
    swapDirection(state) {
      if (state.saving) return;
      [state.subject, state.object] = [state.object, state.subject];
      editing(state);
    },
    editDraft(
      state,
      action: PayloadAction<
        Partial<Pick<AuthoringDraft, "predicate" | "author" | "comment" | "confidence">>
      >,
    ) {
      if (state.saving) return;
      Object.assign(state, action.payload);
      editing(state);
    },
    reviewRow(
      state,
      action: PayloadAction<{ id: string; subject: string; object: string; predicate: string }>,
    ) {
      if (state.saving) return;
      state.reviewId = action.payload.id;
      state.subject = { schema: "", id: action.payload.subject };
      state.object = { schema: "", id: action.payload.object };
      state.predicate = action.payload.predicate;
      state.comment = "";
      editing(state);
    },
    clearDraft: () => initialState,
    setSaving(state, action: PayloadAction<boolean>) {
      state.saving = action.payload;
      if (action.payload) state.error = "";
    },
    /** A save that reached the store. The draft is gone; only the report remains. */
    saved(state, action: PayloadAction<string>) {
      Object.assign(state, initialState, { message: action.payload });
    },
    /** A save that did not. Everything the human typed is still here. */
    failed(state, action: PayloadAction<string>) {
      state.error = action.payload;
      state.message = "";
      state.saving = false;
    },
  },
});

export const { usePair, swapDirection, editDraft, reviewRow, clearDraft, setSaving, saved, failed } =
  authoringSlice.actions;

/** Whether the draft carries everything a record needs. */
export function isComplete(draft: AuthoringDraft): boolean {
  const confidence = Number(draft.confidence);
  return (
    draft.subject !== null &&
    draft.object !== null &&
    draft.author.trim() !== "" &&
    draft.comment.trim() !== "" &&
    draft.confidence !== "" &&
    Number.isFinite(confidence) &&
    confidence >= 0 &&
    confidence <= 1
  );
}

/** The one sentence the interface uses everywhere to say where the draft stands. */
export function saveStatus(draft: AuthoringDraft, busy: boolean): string {
  if (busy || draft.saving) return "Saving…";
  if (draft.dirty) return "Unsaved changes";
  return draft.message === "" ? "No unsaved changes" : draft.message;
}
