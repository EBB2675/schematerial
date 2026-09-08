import { useMemo, useState } from "react";

import { useMappingsQuery } from "../api";
import { reviewRow } from "../authoringSlice";
import { idPrefix, predicateLabel, snapshotLabel, statusLabel } from "../format";
import { countByStatus } from "../mappings";
import { useAppDispatch, useAppSelector } from "../store";
import type { MappingRow } from "../types";
import { setAuthoring } from "../uiSlice";

import { Copyable } from "./Copyable";

const FILTERS = ["all", "accepted", "suggested", "rejected"] as const;
type Filter = (typeof FILTERS)[number];

function matches(row: MappingRow, query: string): boolean {
  if (query === "") return true;
  const text = [
    row.subject_id,
    row.object_id,
    row.predicate_id,
    row.author_id,
    row.comment,
    row.subject_snapshot?.name ?? "",
    row.object_snapshot?.name ?? "",
  ]
    .join(" ")
    .toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((token) => text.includes(token));
}

/**
 * One end of a saved row: the snapshot's name, with the stored identifier under
 * it. The name may wrap at the dot between the class and the attribute, which
 * is the only place breaking it still reads as the name it is.
 */
function End({ id, row, which }: { id: string; row: MappingRow; which: "subject" | "object" }) {
  const snapshot = which === "subject" ? row.subject_snapshot : row.object_snapshot;
  const label = snapshotLabel(snapshot, id);
  const dot = label.lastIndexOf(".");
  return (
    <div className="cell-end">
      <span className="cell-name">
        {dot > 0 ? (
          <>
            {label.slice(0, dot + 1)}
            <wbr />
            {label.slice(dot + 1)}
          </>
        ) : (
          label
        )}
      </span>
      <span className="cell-id">
        <span className="chip source">{idPrefix(id)}</span>
        <code title={id}>{id}</code>
        <Copyable value={id} label={`the ${which} identifier`} />
      </span>
    </div>
  );
}

/**
 * Everything the crosswalk currently says, as a table.
 *
 * Rejections are rows here rather than absences, because a rejection is the
 * record that stops the same correspondence being proposed again. Superseded
 * records are not shown: the server serves current rows and the file keeps the
 * whole history.
 */
export function MappingsView() {
  const dispatch = useAppDispatch();
  const busy = useAppSelector((state) => state.authoring.saving);
  const { data, isError, isFetching, refetch } = useMappingsQuery();
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  const rows = data?.rows ?? [];
  const counts = useMemo(() => countByStatus(rows), [rows]);
  const shown = useMemo(
    () => rows.filter((row) => (filter === "all" || row.review_status === filter) && matches(row, query)),
    [rows, filter, query],
  );

  return (
    <section className="mappings" aria-label="crosswalk mappings">
      <div className="mappings-bar">
        <div className="segmented" role="group" aria-label="review status">
          {FILTERS.map((option) => (
            <button
              key={option}
              type="button"
              className={filter === option ? "active" : ""}
              onClick={() => setFilter(option)}
            >
              {option === "all" ? "all" : statusLabel(option)}
              <span className="tab-count">
                {option === "all" ? rows.length : (counts[option] ?? 0)}
              </span>
            </button>
          ))}
        </div>
        <input
          type="search"
          className="search"
          value={query}
          placeholder="filter by element, author or justification"
          aria-label="filter mappings"
          onChange={(event) => setQuery(event.target.value)}
        />
        <button type="button" className="btn" disabled={isFetching} onClick={() => void refetch()}>
          Reload mappings
        </button>
      </div>

      {isError && (
        <p className="alert" role="alert">
          Mappings could not be loaded. Start the server with mapping storage enabled.
        </p>
      )}

      {isError ? null : shown.length === 0 ? (
        <p className="empty-state">
          {rows.length === 0
            ? "No mappings yet. In Align, select an element on each side and choose Create mapping."
            : "No mapping matches this filter."}
        </p>
      ) : (
        <div className="table-scroll">
          <table className="mapping-table" aria-label="saved mappings">
            <thead>
              <tr>
                <th scope="col">status</th>
                <th scope="col">subject</th>
                <th scope="col">predicate</th>
                <th scope="col">object</th>
                <th scope="col">author</th>
                <th scope="col">date</th>
                <th scope="col">confidence</th>
                <th scope="col">justification</th>
                <th scope="col">
                  <span className="sr-only">action</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((row) => (
                <tr key={row.record_id}>
                  <td>
                    <span className={`state ${statusLabel(row.review_status)}`}>
                      {statusLabel(row.review_status)}
                    </span>
                  </td>
                  <td>
                    <End id={row.subject_id} row={row} which="subject" />
                  </td>
                  <td>
                    <strong className="predicate">{predicateLabel(row.predicate_id)}</strong>
                  </td>
                  <td>
                    <End id={row.object_id} row={row} which="object" />
                  </td>
                  <td className="wrap">{row.author_id}</td>
                  <td className="date">{row.mapping_date}</td>
                  <td className="numeric">{row.confidence}</td>
                  <td className="wrap justification">{row.comment}</td>
                  <td>
                    <button
                      type="button"
                      className="btn"
                      disabled={busy}
                      onClick={() => {
                        dispatch(
                          reviewRow({
                            id: row.record_id,
                            subject: row.subject_id,
                            object: row.object_id,
                            predicate: row.predicate_id,
                          }),
                        );
                        dispatch(setAuthoring(true));
                      }}
                    >
                      {row.review_status === "suggested" ? "Review suggestion" : "Correct mapping"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
