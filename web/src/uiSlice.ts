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

/**
 * The two things the workspace is for: reading the schemas next to each other,
 * and reading back what has been written about them. They are separate views
 * rather than two panels competing for the same window, because browsing wants
 * every row of height it can get and a crosswalk table wants width.
 */
export type Workspace = "align" | "mappings";

/**
 * Which side is the subject of a mapping written from the current pair.
 *
 * A correspondence is directional, so this is a decision a person makes rather
 * than a consequence of which pane a schema happened to be opened in. It is held
 * here, next to the panes, so the direction is visible and reversible before any
 * form is opened.
 */
export type PairDirection = "lr" | "rl";

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
  /** Whether this side's detail region is open under its list. */
  detail: boolean;
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
  /** Which of the two workspaces is on screen. */
  workspace: Workspace;
  /** Whether the PMDco dock is open. It stays closed until a person asks for it. */
  pmdco: boolean;
  /** Which side the pair reads from. Left to right unless the reader swapped it. */
  direction: PairDirection;
  /**
   * Whether the authoring drawer is on screen. Closing it hides the form and
   * keeps the draft, so a stray Escape cannot discard unsaved work.
   */
  authoring: boolean;
}

function emptyPane(): PaneState {
  return {
    schema: null,
    view: "list",
    selected: null,
    linked: true,
    filters: { ...EMPTY_FILTERS },
    detail: true,
  };
}

const initialState: UiState = {
  panes: { left: emptyPane(), right: emptyPane() },
  shared: { ...EMPTY_FILTERS },
  active: "left",
  focusRequests: 0,
  expanded: null,
  opened: false,
  workspace: "align",
  pmdco: false,
  direction: "lr",
  authoring: false,
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
    /** Open or close one side's detail region without touching the other side. */
    setDetail(state, action: PayloadAction<{ side: Side; open: boolean }>) {
      state.panes[action.payload.side].detail = action.payload.open;
    },
    setWorkspace(state, action: PayloadAction<Workspace>) {
      state.workspace = action.payload;
    },
    setPmdco(state, action: PayloadAction<boolean>) {
      state.pmdco = action.payload;
    },
    /** Turn the pair round, so the other side becomes the subject. */
    swapPair(state) {
      state.direction = state.direction === "lr" ? "rl" : "lr";
    },
    /**
     * Show or hide the authoring form. This is presentation only: the draft it
     * edits lives in its own slice and survives the drawer being closed, so a
     * stray Escape never costs unsaved work.
     */
    setAuthoring(state, action: PayloadAction<boolean>) {
      state.authoring = action.payload;
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
  setDetail,
  setWorkspace,
  setPmdco,
  swapPair,
  setAuthoring,
} = uiSlice.actions;
