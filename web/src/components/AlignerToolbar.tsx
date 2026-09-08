import { useAppDispatch, useAppSelector } from "../store";
import { setKind, setOnlyDiagnostics, setOnlyInherited, setQuery } from "../uiSlice";
import type { SchemaSummary } from "../types";

import { FilterControls } from "./FilterControls";

/**
 * The shared search, and what the sides are doing with it.
 *
 * One query filters both sides at once, because the reason for reading two
 * schemas together is to look for the same idea in each. Scroll and selection
 * are deliberately not shared: the schemas have no common structure, so a
 * position in one names nothing in the other.
 */
export function AlignerToolbar({ schemas }: { schemas: SchemaSummary[] }) {
  const dispatch = useAppDispatch();
  const shared = useAppSelector((state) => state.ui.shared);
  const panes = useAppSelector((state) => state.ui.panes);
  const open = [panes.left, panes.right].filter((pane) => pane.schema !== null);
  const followers = open.filter((pane) => pane.linked).length;
  const bothSides = panes.left.schema !== null && panes.right.schema !== null;
  const sameSchema = bothSides && panes.left.schema === panes.right.schema;
  const total = schemas.length;

  return (
    <header className="toolbar">
      <div className="toolbar-top">
        <h1>schematerial</h1>
        <p className="subtle">
          {total} schema{total === 1 ? "" : "s"} loaded · read-only: nothing here creates,
          scores or stores a mapping
        </p>
      </div>
      <FilterControls
        side={null}
        filters={shared}
        disabled={followers === 0}
        label="shared search"
        onQuery={(value) => dispatch(setQuery({ side: null, value }))}
        onKind={(value) => dispatch(setKind({ side: null, value }))}
        onInherited={(value) => dispatch(setOnlyInherited({ side: null, value }))}
        onDiagnostics={(value) => dispatch(setOnlyDiagnostics({ side: null, value }))}
      />
      <p className="subtle hint">
        {followers === 0
          ? "Both sides are searching on their own; this search filters neither."
          : `Filters ${followers === 2 ? "both sides" : "one side"}. ` +
            "Searching never reaches the server."}
        {" · arrow keys, Page Up/Down and Home/End move the active side; "}
        <kbd>[</kbd> and <kbd>]</kbd> switch sides
      </p>
      {sameSchema && (
        <p className="notice-inline" role="status">
          Both sides show <code>{panes.left.schema}</code>. This is a schema compared with
          itself — useful for reading one large schema in two places at once, and not a
          correspondence between two sources.
        </p>
      )}
    </header>
  );
}
