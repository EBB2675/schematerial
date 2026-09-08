import type { KeyboardEvent } from "react";

import type { Side } from "../panes";
import type { Filters, KindFilter } from "../search";

const KINDS: { value: KindFilter; label: string }[] = [
  { value: "all", label: "all" },
  { value: "class", label: "classes" },
  { value: "attribute", label: "attributes" },
];

/**
 * One search box and its filters.
 *
 * The same control serves the shared search above both panes and the private
 * search an unlinked pane gets, so the two cannot drift apart in behaviour.
 * `side` is null for the shared instance and names the pane for a private one;
 * it only distinguishes the accessible names.
 */
export function FilterControls({
  side,
  filters,
  label,
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
  disabled?: boolean;
  onQuery: (value: string) => void;
  onKind: (value: KindFilter) => void;
  onInherited: (value: boolean) => void;
  onDiagnostics: (value: boolean) => void;
  onArrowDown?: () => void;
}) {
  const scope = side === null ? "shared" : side;
  return (
    <div className={`controls${disabled ? " disabled" : ""}`}>
      <input
        type="search"
        className="search"
        value={filters.query}
        disabled={disabled}
        placeholder="search a name, class, range or unit"
        aria-label={label}
        onChange={(event) => onQuery(event.target.value)}
        onKeyDown={(event: KeyboardEvent<HTMLInputElement>) => {
          if (event.key === "ArrowDown" && onArrowDown !== undefined) {
            onArrowDown();
            event.preventDefault();
          }
        }}
      />
      <div className="filters">
        <div className="kinds" role="group" aria-label={`element kind, ${label}`}>
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
    </div>
  );
}
