import { schemaLabel } from "../format";
import { sideLabel, type Side } from "../panes";
import { useAppDispatch, useAppSelector } from "../store";
import type { SchemaSummary } from "../types";
import { chooseSchema, setDetail, setExpanded, setLinked, setView, type PaneView } from "../uiSlice";

const number = new Intl.NumberFormat("en");

const VIEWS: { value: PaneView; label: string }[] = [
  { value: "list", label: "list" },
  { value: "graph", label: "graph" },
];

/**
 * Counts are labelled rather than merged into a single "elements" figure:
 * effective attributes, browsable rows and contextual snapshot paths are three
 * different numbers over the same schema, and conflating them hides real
 * structure. They live behind a disclosure because that distinction matters when
 * a conversion is being questioned and never while a list is being read.
 */
function Details({ summary }: { summary: SchemaSummary }) {
  const counts = summary.counts;
  const items: { label: string; value: number; hint: string }[] = [
    { label: "classes", value: counts.classes, hint: "Source sections converted to classes." },
    {
      label: "effective attributes",
      value: counts.effective_attributes,
      hint: "Attributes visible on a class, declared locally or inherited.",
    },
    {
      label: "of them inherited",
      value: counts.inherited_attributes,
      hint: "Effective attributes declared on an ancestor rather than the class itself.",
    },
    {
      label: "browsable elements",
      value: counts.browsable_elements,
      hint: "Rows in the index: one per class plus one per effective attribute.",
    },
    {
      label: "snapshot paths",
      value: counts.snapshot_paths,
      hint:
        "Contextual positions reached from a root through subsections. " +
        "One declaration has many, so this is not an element count.",
    },
    { label: "enums", value: counts.enums, hint: "Enumerations carried over from the source." },
    {
      label: "diagnostics",
      value: summary.diagnostics.total ?? 0,
      hint: "Conversion reports attached to the classes and attributes they concern.",
    },
  ];
  const breakdown = Object.entries(summary.diagnostics).filter(([key]) => key !== "total");
  return (
    <details className="disclosure counts-disclosure">
      <summary aria-label={`counts and diagnostics, ${schemaLabel(summary)}`} title="Counts and diagnostics">
        <span aria-hidden="true">details</span>
      </summary>
      <div className="disclosure-panel wide">
        <dl className="counts">
          {items.map((item) => (
            <div key={item.label} className="count" title={item.hint}>
              <dt>{item.label}</dt>
              <dd>{number.format(item.value)}</dd>
            </div>
          ))}
        </dl>
        {breakdown.length > 0 && (
          <p className="subtle">
            Diagnostics:{" "}
            {breakdown.map(([status, value]) => `${number.format(value)} ${status}`).join(", ")}
          </p>
        )}
        <p className="subtle">
          <code>{summary.name}</code> — read-only. Counts are three different numbers over the same
          schema and are never merged.
        </p>
      </div>
    </details>
  );
}

/**
 * One side's header, on one line: what it shows, and the few controls that
 * change how it shows it.
 *
 * Either side may be closed, which is how a single full-width schema is read
 * without a second interface, and either side may show any loaded schema —
 * including the one already on the other side. The picker is the title, so the
 * header spends no height saying the same name twice.
 */
export function PaneHeader({
  side,
  schemas,
  current,
  active,
}: {
  side: Side;
  schemas: SchemaSummary[];
  current: SchemaSummary | null;
  active: boolean;
}) {
  const dispatch = useAppDispatch();
  const pane = useAppSelector((state) => state.ui.panes[side]);
  const expanded = useAppSelector((state) => state.ui.expanded === side);
  const browsable = current !== null && current.status === "ok";
  const where = sideLabel(side);

  return (
    <header className={`pane-header${active ? " active" : ""}`}>
      <h2 className="sr-only">{current === null ? `${where} side, closed` : schemaLabel(current)}</h2>
      <select
        className="pane-picker"
        value={current?.name ?? ""}
        aria-label={`schema on the ${where}`}
        title={current?.name ?? "no schema on this side"}
        onChange={(event) =>
          dispatch(
            chooseSchema({ side, schema: event.target.value === "" ? null : event.target.value }),
          )
        }
      >
        <option value="">no schema — close this side</option>
        {schemas.map((schema) => (
          <option key={schema.name} value={schema.name}>
            {schemaLabel(schema)}
            {schema.status === "ok" ? "" : " — unsupported"}
          </option>
        ))}
      </select>

      {browsable && (
        <div className="pane-controls">
          <Details summary={current} />
          <div className="segmented" role="group" aria-label={`view on the ${where}`}>
            {VIEWS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={pane.view === option.value ? "active" : ""}
                onClick={() => dispatch(setView({ side, view: option.value }))}
              >
                {option.label}
              </button>
            ))}
          </div>
          <label className="check" title="Stop following the shared search">
            <input
              type="checkbox"
              checked={!pane.linked}
              aria-label={`search the ${where} side on its own`}
              onChange={(event) => dispatch(setLinked({ side, linked: !event.target.checked }))}
            />
            own search
          </label>
          <button
            type="button"
            className="toggle"
            aria-pressed={pane.detail}
            aria-label={`${pane.detail ? "collapse" : "expand"} the ${where} detail`}
            title={pane.detail ? "Collapse the detail region" : "Expand the detail region"}
            onClick={() => dispatch(setDetail({ side, open: !pane.detail }))}
          >
            detail
          </button>
          <button
            type="button"
            className="toggle"
            aria-pressed={expanded}
            aria-label={`${expanded ? "collapse" : "expand"} the ${where} side`}
            title={expanded ? "Show both sides again (Escape)" : "Give this side the whole window"}
            onClick={() => dispatch(setExpanded(expanded ? null : side))}
          >
            {expanded ? "both sides" : "full width"}
          </button>
        </div>
      )}
    </header>
  );
}
