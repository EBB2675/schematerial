import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

export interface MappingEnd { schema: string; id: string }
export interface AuthoringDraft {
  subject: MappingEnd | null;
  object: MappingEnd | null;
  predicate: string;
  author: string;
  comment: string;
  confidence: string;
  reviewId: string | null;
  dirty: boolean;
  saving: boolean;
}
const initialState: AuthoringDraft = {
  subject: null, object: null, predicate: "skos:closeMatch", author: "", comment: "",
  confidence: "1", reviewId: null, dirty: false, saving: false,
};
export const authoringSlice = createSlice({
  name: "authoring", initialState,
  reducers: {
    usePair(state, action: PayloadAction<{ subject: MappingEnd; object: MappingEnd }>) {
      if (state.saving) return;
      Object.assign(state, action.payload, { reviewId: null, dirty: true });
    },
    swapDirection(state) {
      if (state.saving) return;
      [state.subject, state.object] = [state.object, state.subject];
      state.dirty = true;
    },
    editDraft(state, action: PayloadAction<Partial<Pick<AuthoringDraft,
      "predicate" | "author" | "comment" | "confidence">>>) {
      if (state.saving) return;
      Object.assign(state, action.payload, { dirty: true });
    },
    reviewRow(state, action: PayloadAction<{ id: string; subject: string; object: string;
      predicate: string }>) {
      if (state.saving) return;
      state.reviewId = action.payload.id;
      state.subject = { schema: "", id: action.payload.subject };
      state.object = { schema: "", id: action.payload.object };
      state.predicate = action.payload.predicate;
      state.comment = "";
      state.dirty = true;
    },
    clearDraft: () => initialState,
    setSaving(state, action: PayloadAction<boolean>) { state.saving = action.payload; },
  },
});
export const { usePair, swapDirection, editDraft, reviewRow, clearDraft, setSaving } = authoringSlice.actions;
