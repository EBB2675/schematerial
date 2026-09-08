import type { KeyboardEvent } from "react";

import type { Side } from "../panes";
import type { Filters, KindFilter } from "../search";

const KINDS: { value: KindFilter; label: string }[] = [
  { value: "all", label: "all" },
  { value: "class", label: "classes" },
  { value: "attribute", label: "attributes" },
];

/**
 * One search box and its filters, on a single line.
 *
 * The same control serves the shared search above both panes and the private
 * search an unlinked pane gets, so the two cannot drift apart in behaviour.
 * `side` is null for the shared instance and names the pane for a private one;
 * it only distinguishes the accessible names.
 *
 * The kind filter stays on the line because it is used constantly. The two
 * narrower filters sit behind a disclosure: still one click away, no longer
 * occupying a row of the window in every session that never touches them.
 */
export function FilterControls({
  side,
  filters,
  label,
  placeholder = "search a name, class, range or unit",
  disabled = false,
  onQuery,
  onKind,
  onInherited,
  onDiagnostics,
  onArrowDown,
}: {
  side: Side | null;
  filters: Filters;
  label: string;
  placeholder?: string;
  disabled?: boolean;
  onQuery: (value: string) => void;
  onKind: (value: KindFilter) => void;
  onInherited: (value: boolean) => void;
  onDiagnostics: (value: boolean) => void;
  onArrowDown?: () => void;
}) {
  const scope = side === null ? "shared" : side;
  const narrowed = filters.onlyInherited || filters.onlyDiagnostics;
  return (
    <div className={`controls${disabled ? " disabled" : ""}`}>
      <input
        type="search"
        className="search"
        value={filters.query}
        disabled={disabled}
        placeholder={placeholder}
        aria-label={label}
        onChange={(event) => onQuery(event.target.value)}
        onKeyDown={(event: KeyboardEvent<HTMLInputElement>) => {
          if (event.key === "ArrowDown" && onArrowDown !== undefined) {
            onArrowDown();
            event.preventDefault();
          }
        }}
      />
      <div className="segmented" role="group" aria-label={`element kind, ${label}`}>
        {KINDS.map((option) => (
          <button
            key={option.value}
            type="button"
            disabled={disabled}
            className={filters.kind === option.value ? "active" : ""}
            onClick={() => onKind(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      <details className="disclosure filters">
        <summary aria-label={`more filters, ${label}`} title="More filters">
          <span aria-hidden="true">filters</span>
          {narrowed && <span className="dot" aria-hidden="true" />}
        </summary>
        <div className="disclosure-panel">
          <label>
            <input
              type="checkbox"
              checked={filters.onlyInherited}
              disabled={disabled}
              aria-label={`inherited only, ${scope}`}
              onChange={(event) => onInherited(event.target.checked)}
            />
            inherited only
          </label>
          <label>
            <input
              type="checkbox"
              checked={filters.onlyDiagnostics}
              disabled={disabled}
              aria-label={`with diagnostics, ${scope}`}
              onChange={(event) => onDiagnostics(event.target.checked)}
            />
            with diagnostics
          </label>
        </div>
      </details>
    </div>
  );
}
