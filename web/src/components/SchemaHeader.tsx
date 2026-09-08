import { sideLabel, type Side } from "../panes";
import { useAppDispatch, useAppSelector } from "../store";
import type { SchemaSummary } from "../types";
import { chooseSchema, setExpanded, setLinked, setView, type PaneView } from "../uiSlice";

const number = new Intl.NumberFormat("en");

const VIEWS: { value: PaneView; label: string }[] = [
  { value: "list", label: "list" },
  { value: "graph", label: "graph" },
];

/**
 * Counts are labelled rather than merged into a single "elements" figure:
 * effective attributes, browsable rows and contextual snapshot paths are three
 * different numbers over the same schema, and conflating them hides real
 * structure.
 */
function Counts({ summary }: { summary: SchemaSummary }) {
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
  return (
    <dl className="counts">
      {items.map((item) => (
        <div key={item.label} className="count" title={item.hint}>
          <dt>{item.label}</dt>
          <dd>{number.format(item.value)}</dd>
        </div>
      ))}
    </dl>
  );
}

/**
 * One side's header: which schema it shows, where that schema came from, and
 * whether it follows the shared search.
 *
 * Either side may be closed, which is how a single full-width schema is read
 * without a second interface, and either side may show any loaded schema —
 * including the one already on the other side.
 */
export function SchemaHeader({
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
  const linked = useAppSelector((state) => state.ui.panes[side].linked);
  const view = useAppSelector((state) => state.ui.panes[side].view);
  const expanded = useAppSelector((state) => state.ui.expanded === side);
  const source = current?.source;
  return (
    <header className={`header${active ? " active" : ""}`}>
      <div className="header-top">
        <label className="schema-picker">
          <span>{sideLabel(side)} schema</span>
          <select
            value={current?.name ?? ""}
            aria-label={`schema on the ${sideLabel(side)}`}
            onChange={(event) =>
              dispatch(
                chooseSchema({
                  side,
                  schema: event.target.value === "" ? null : event.target.value,
                }),
              )
            }
          >
            <option value="">none — close this side</option>
            {schemas.map((schema) => (
              <option key={schema.name} value={schema.name}>
                {schema.name}
                {schema.status === "ok" ? "" : " — unsupported"}
              </option>
            ))}
          </select>
        </label>
        <div className="schema-identity">
          <h2>{current === null ? "No schema" : (current.title ?? current.name)}</h2>
          <p className="subtle">
            {current === null ? (
              "closed"
            ) : (
              <>
                <code>{current.name}</code>
                {source?.package != null && (
                  <>
                    {" · "}
                    {source.package}
                    {source.version !== null && ` ${source.version}`}
                  </>
                )}
                {current.status === "ok" && " · read-only"}
              </>
            )}
          </p>
        </div>
        {current !== null && current.status === "ok" && (
          <div className="kinds views" role="group" aria-label={`view on the ${sideLabel(side)}`}>
            {VIEWS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={view === option.value ? "active" : ""}
                onClick={() => dispatch(setView({ side, view: option.value }))}
              >
                {option.label}
              </button>
            ))}
          </div>
        )}
        {current !== null && current.status === "ok" && (
          <button
            type="button"
            className="expander"
            aria-label={`${expanded ? "collapse" : "expand"} the ${sideLabel(side)} side`}
            title={
              expanded
                ? "Show both sides again (Escape)"
                : "Give this side the whole window"
            }
            onClick={() => dispatch(setExpanded(expanded ? null : side))}
          >
            {expanded ? "collapse" : "expand"}
          </button>
        )}
        {current !== null && current.status === "ok" && (
          <label className="link-toggle" title="Stop following the shared search above">
            <input
              type="checkbox"
              checked={!linked}
              aria-label={`search the ${sideLabel(side)} side on its own`}
              onChange={(event) => dispatch(setLinked({ side, linked: !event.target.checked }))}
            />
            own search
          </label>
        )}
      </div>
      {current !== null && current.status === "ok" && view === "list" && (
        <Counts summary={current} />
      )}
    </header>
  );
}
