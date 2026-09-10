import { schemaLabel } from "../format";
import type { SchemaSummary } from "../types";

/**
 * Keyboard help and the technical record of what was loaded.
 *
 * None of this belongs in the reading flow, and all of it has to be findable.
 * Cache keys, toolchain pins, schema identifiers and dependency versions are
 * what an argument about a conversion is settled with; they are one click away
 * and nowhere near the element a person is looking at.
 */
export function HelpMenu({ schemas }: { schemas: SchemaSummary[] }) {
  return (
    <details className="disclosure help">
      <summary aria-label="help, keyboard shortcuts and loaded schemas" title="Help">
        <span aria-hidden="true">?</span>
      </summary>
      <div className="disclosure-panel wide">
        <h3>Keyboard</h3>
        <dl className="shortcuts">
          <div>
            <dt>
              <kbd>[</kbd> <kbd>]</kbd>
            </dt>
            <dd>hand the keyboard to the left or right side</dd>
          </div>
          <div>
            <dt>
              <kbd>↑</kbd> <kbd>↓</kbd>
            </dt>
            <dd>move through the active side</dd>
          </div>
          <div>
            <dt>
              <kbd>Page Up</kbd> <kbd>Page Down</kbd> <kbd>Home</kbd> <kbd>End</kbd>
            </dt>
            <dd>move further through the active side</dd>
          </div>
          <div>
            <dt>
              <kbd>/</kbd>
            </dt>
            <dd>go to the shared search</dd>
          </div>
          <div>
            <dt>
              <kbd>Esc</kbd>
            </dt>
            <dd>close the drawer or panel, then give both sides the window back</dd>
          </div>
        </dl>

        <h3>How the two sides work</h3>
        <p>
          The shared search filters every side that follows it; a side can search on its own from
          its own header. Searching never reaches the server: each schema&rsquo;s index is fetched
          once and filtered in the page. Scroll position and selection stay per side, because a row
          in one schema names nothing in the other.
        </p>

        <h3>The class graph</h3>
        <p>
          Class positions are laid out once when a document is ingested and served with the graph,
          so selecting, hovering, panning or searching never moves a box. A search dims the classes
          it does not reach rather than removing them, because dropping a class would silently cut
          the edges running through it.
        </p>

        <h3>Loaded schemas</h3>
        <ul className="loaded">
          {schemas.map((schema) => (
            <li key={schema.name}>
              <span className="loaded-name">
                {schemaLabel(schema)}
                {schema.status === "ok" ? "" : " — unsupported"}
              </span>
              <code>{schema.name}</code>
              {schema.schema_id !== null && <code className="subtle">{schema.schema_id}</code>}
              <dl className="meta">
                {schema.source.package !== null && (
                  <div>
                    <dt>source</dt>
                    <dd>
                      {schema.source.package} {schema.source.version ?? ""}
                    </dd>
                  </div>
                )}
                {Object.entries(schema.source.dependencies ?? {}).map(([name, version]) => (
                  <div key={name}>
                    <dt>{name}</dt>
                    <dd>{version}</dd>
                  </div>
                ))}
                {Object.entries(schema.toolchain ?? {}).map(([name, version]) => (
                  <div key={name}>
                    <dt>{name}</dt>
                    <dd>{version}</dd>
                  </div>
                ))}
                {schema.cache_key !== null && (
                  <div>
                    <dt>cache key</dt>
                    <dd>
                      <code>{schema.cache_key.slice(0, 12)}</code>
                    </dd>
                  </div>
                )}
              </dl>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}
