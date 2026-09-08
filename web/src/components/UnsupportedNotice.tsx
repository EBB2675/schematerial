import type { SchemaSummary } from "../types";

/**
 * A refused import is shown with its reason and its diagnostics. Presenting an
 * apparently complete pane over a conversion nobody vouched for would be worse
 * than showing the failure.
 */
export function UnsupportedNotice({ summary }: { summary: SchemaSummary }) {
  return (
    <section className="unsupported">
      <h2>This schema was not accepted as a faithful import</h2>
      <pre className="error-text">{summary.error}</pre>
      {summary.schema_diagnostics.length > 0 && (
        <>
          <h3>Diagnostics ({summary.schema_diagnostics.length})</h3>
          <ul className="diagnostics">
            {summary.schema_diagnostics.map((entry, index) => (
              <li key={`${entry.path}-${index}`}>
                <span className={`badge status-${entry.status}`}>{entry.status}</span>
                <code>{entry.path}</code>
                <span>{entry.reason}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
