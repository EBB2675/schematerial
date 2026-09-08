import { useMappingsQuery } from "../api";
import { saveStatus } from "../authoringSlice";
import { useAppDispatch, useAppSelector } from "../store";
import type { SchemaSummary } from "../types";
import {
  setKind,
  setOnlyDiagnostics,
  setOnlyInherited,
  setPmdco,
  setQuery,
  setWorkspace,
  type Workspace,
} from "../uiSlice";

import { FilterControls } from "./FilterControls";
import { HelpMenu } from "./HelpMenu";
import { ThemeToggle } from "./ThemeToggle";

const TABS: { value: Workspace; label: string }[] = [
  { value: "align", label: "Align" },
  { value: "mappings", label: "Mappings" },
];

/**
 * The one bar above everything: where you are, what you are searching for, and
 * whether anything is unsaved.
 *
 * It carries a single line of controls on purpose. Every count, every
 * explanation of how the sides are synchronised and every keyboard shortcut used
 * to sit here in prose; they are still reachable, from the help menu and from
 * each side's own details, but they no longer spend the height the two panes
 * need in order to be the workspace.
 */
export function AppBar({ schemas }: { schemas: SchemaSummary[] }) {
  const dispatch = useAppDispatch();
  const shared = useAppSelector((state) => state.ui.shared);
  const panes = useAppSelector((state) => state.ui.panes);
  const workspace = useAppSelector((state) => state.ui.workspace);
  const pmdco = useAppSelector((state) => state.ui.pmdco);
  const draft = useAppSelector((state) => state.authoring);
  const { data } = useMappingsQuery();

  const followers = [panes.left, panes.right].filter(
    (pane) => pane.schema !== null && pane.linked,
  ).length;
  const sameSchema = panes.left.schema !== null && panes.left.schema === panes.right.schema;
  const rows = data?.rows.length;
  const status = saveStatus(draft, false);

  return (
    <header className="appbar">
      <div className="appbar-row">
        <span className="brand">schematerial</span>
        <nav className="tabs" role="tablist" aria-label="workspace">
          {TABS.map((tab) => (
            <button
              key={tab.value}
              type="button"
              role="tab"
              id={`tab-${tab.value}`}
              aria-selected={workspace === tab.value}
              aria-controls={`workspace-${tab.value}`}
              className={workspace === tab.value ? "tab active" : "tab"}
              onClick={() => dispatch(setWorkspace(tab.value))}
            >
              {tab.label}
              {tab.value === "mappings" && rows !== undefined && (
                <span className="tab-count">{rows}</span>
              )}
            </button>
          ))}
        </nav>

        {/* The shared search filters the panes. The Mappings table has its own
            filter, and two search boxes that mean different things would be
            worse than one that is only there when it does something. */}
        {workspace === "align" && (
          <FilterControls
            side={null}
            filters={shared}
            disabled={followers === 0}
            label="shared search"
            placeholder={followers === 0 ? "no side follows this search" : "search both sides"}
            onQuery={(value) => dispatch(setQuery({ side: null, value }))}
            onKind={(value) => dispatch(setKind({ side: null, value }))}
            onInherited={(value) => dispatch(setOnlyInherited({ side: null, value }))}
            onDiagnostics={(value) => dispatch(setOnlyDiagnostics({ side: null, value }))}
          />
        )}

        <div className="appbar-end">
          <span className={`save-status${draft.dirty ? " dirty" : ""}`} role="status">
            {status}
          </span>
          <button
            type="button"
            className={`toggle${pmdco ? " on" : ""}`}
            aria-pressed={pmdco}
            aria-label="PMDco taxonomy panel"
            onClick={() => dispatch(setPmdco(!pmdco))}
          >
            PMDco
          </button>
          <ThemeToggle />
          <HelpMenu schemas={schemas} />
        </div>
      </div>
      {sameSchema && (
        <p className="appbar-note">
          Both sides show <code>{panes.left.schema}</code>. This is a schema compared with itself,
          not a correspondence between two sources.
        </p>
      )}
    </header>
  );
}
