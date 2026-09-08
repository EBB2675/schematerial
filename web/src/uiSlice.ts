/**
 * Interface state: which schema each side shows, what is being searched for,
 * what each side has selected and which side the keyboard drives. Server data
 * lives in the RTK Query cache, never here.
 *
 * Two schemas share no structure, so the sides are synchronised only where that
 * means something. Search and filters are shared by default, because looking for
 * the same word on both sides is the whole point of a side-by-side reading.
 * Scroll position and selection stay per side: a row index in one schema names
 * nothing in the other, and each side keeps its selection while the other side
 * is being driven.
 */

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

import { defaultPair, type Pair, type Side } from "./panes";
import { EMPTY_FILTERS, type Filters, type KindFilter } from "./search";
import type { SchemaSummary } from "./types";

/** How a side shows its schema: as a list of elements, or as a class graph. */
export type PaneView = "list" | "graph";

export interface PaneState {
  /** The schema shown here, or null when this side is closed. */
  schema: string | null;
  /** Chosen per side, so a list can be read against a graph. */
  view: PaneView;
  /** The selected class-scoped element identifier. Kept while the side is inactive. */
  selected: string | null;
  /** True while this side follows the shared search and filters. */
  linked: boolean;
  /** This side's own search and filters, used only while it is unlinked. */
  filters: Filters;
}

export interface UiState {
  panes: Record<Side, PaneState>;
  /** The search and filters every linked side follows. */
  shared: Filters;
  /** The side the keyboard drives. The other side keeps its own selection. */
  active: Side;
  /**
   * Bumped only when the keyboard is *handed* to a side, which is what moves
   * the caret into its list. Focus arriving by click or Tab activates a side
   * without this, so clicking into a control does not throw focus elsewhere.
   */
  focusRequests: number;
  /** A side given the whole window, or null while both are shown. */
  expanded: Side | null;
  /** True once the opening pair has been chosen from the catalogue. */
  opened: boolean;
}

function emptyPane(): PaneState {
  return {
    schema: null,
    view: "list",
    selected: null,
    linked: true,
    filters: { ...EMPTY_FILTERS },
  };
}

const initialState: UiState = {
  panes: { left: emptyPane(), right: emptyPane() },
  shared: { ...EMPTY_FILTERS },
  active: "left",
  focusRequests: 0,
  expanded: null,
  opened: false,
};

/** The filters a side is actually filtering by: the shared ones unless it unlinked. */
export function filtersOf(state: UiState, side: Side): Filters {
  const pane = state.panes[side];
  return pane.linked ? state.shared : pane.filters;
}

/**
 * Where a filter edit lands. `side: null` is the shared control; a side writes
 * to the shared filters while it is linked, so a linked pane never quietly
 * accumulates a private query it is not using.
 */
function target(state: UiState, side: Side | null): Filters {
  if (side === null) return state.shared;
  return state.panes[side].linked ? state.shared : state.panes[side].filters;
}

type Edit<T> = PayloadAction<{ side: Side | null; value: T }>;

export const uiSlice = createSlice({
  name: "ui",
  initialState,
  reducers: {
    /** Fill both sides from the catalogue, once, before the user has chosen. */
    open(state, action: PayloadAction<readonly SchemaSummary[]>) {
      if (state.opened) return;
      const pair: Pair = defaultPair(action.payload);
      state.panes.left.schema = pair.left;
      state.panes.right.schema = pair.right;
      state.opened = true;
    },
    chooseSchema(state, action: PayloadAction<{ side: Side; schema: string | null }>) {
      const pane = state.panes[action.payload.side];
      if (pane.schema === action.payload.schema) return;
      pane.schema = action.payload.schema;
      // A selection names an element of one schema and means nothing in another.
      // The query deliberately survives: it is shared across the sides, and
      // clearing it here would wipe the other side's filtering too.
      pane.selected = null;
    },
    setView(state, action: PayloadAction<{ side: Side; view: PaneView }>) {
      state.panes[action.payload.side].view = action.payload.view;
    },
    setQuery(state, action: Edit<string>) {
      target(state, action.payload.side).query = action.payload.value;
    },
    setKind(state, action: Edit<KindFilter>) {
      target(state, action.payload.side).kind = action.payload.value;
    },
    setOnlyInherited(state, action: Edit<boolean>) {
      target(state, action.payload.side).onlyInherited = action.payload.value;
    },
    setOnlyDiagnostics(state, action: Edit<boolean>) {
      target(state, action.payload.side).onlyDiagnostics = action.payload.value;
    },
    /** Detach a side from the shared search, or reattach it. */
    setLinked(state, action: PayloadAction<{ side: Side; linked: boolean }>) {
      const pane = state.panes[action.payload.side];
      if (pane.linked === action.payload.linked) return;
      // Carry the current filters across so nothing on screen jumps at the moment
      // of unlinking; the side simply stops following further shared edits.
      if (!action.payload.linked) pane.filters = { ...state.shared };
      pane.linked = action.payload.linked;
    },
    selectElement(state, action: PayloadAction<{ side: Side; id: string | null }>) {
      state.panes[action.payload.side].selected = action.payload.id;
    },
    /** Give one side the whole window, or give the window back to both. */
    setExpanded(state, action: PayloadAction<Side | null>) {
      state.expanded = action.payload;
      if (action.payload !== null) state.active = action.payload;
    },
    /** Note which side the keyboard reached, without moving the caret. */
    activate(state, action: PayloadAction<Side>) {
      state.active = action.payload;
    },
    /** Hand the keyboard to one side and put the caret in its list. */
    focusSide(state, action: PayloadAction<Side>) {
      state.active = action.payload;
      state.focusRequests += 1;
    },
  },
});

export const {
  open,
  chooseSchema,
  setView,
  setQuery,
  setKind,
  setOnlyInherited,
  setOnlyDiagnostics,
  setLinked,
  selectElement,
  activate,
  focusSide,
  setExpanded,
} = uiSlice.actions;
