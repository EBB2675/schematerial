# 008. Manual review boundary

Status: approved by the user on 2026-09-08; implemented in Card 12.

The existing web-layer decision specifies a read-only service and explicitly
excludes authoring. Card 12 introduces writes and therefore needs an explicit
trust model for its human review boundary.

## Local single-user model

The operator runs the app on loopback. Dedicated human-review routes are called
only by explicit Save, Accept, or Reject form submissions. They validate the
selected IDs against the prepared schema tables, capture the corresponding
snapshots on the server, and require author identity and justification. Automated
suggestion APIs cannot request acceptance. Acceptance has no score-based path.

Browser writes use a session-bound anti-CSRF token and same-origin checks. A
claimed boolean such as `human: true` is not sufficient authorization. This
protects against unrelated websites issuing writes, but does not authenticate a
person against another process controlled by the same local operator. A local
operator could deliberately imitate the browser protocol; the app cannot prove
physical human presence. Agents and matchers are not given a review client.

No accounts, shared deployment, or identity verification are introduced in this
model. Supporting remote users would require a separate authentication and
review-permission design before enabling writes beyond loopback.

The existing SSSOM store persists the review. Its default location can be
`runs/crosswalk.sssom.tsv`, with an explicit CLI option for another path. Draft
state lives in Redux, with a visible unsaved indication and navigation warning.
Failed saves retain the draft and show an error; successful saves refresh mapping
indicators and review rows. Direction is explicit in the form.

## Validation

Frontend interaction tests cover both source directions, directional predicates,
review actions, draft retention on failure, and visible mapping state. Backend
integration tests cover persistence after restart, server-owned snapshots,
rejection persistence, missing/invalid review authorization, and automated writes
remaining suggestion-only. Structural acceptance guards stay active outside the
narrow human review boundary, supplemented by behavioral tests of that boundary.


## Implementation details and limits

The CLI defaults to `runs/crosswalk.sssom.tsv`; `--mappings PATH` selects another
file. `create_app` accepts an explicit mapping path, preserving read-only use
when no path is supplied. Browser writes require a loopback peer and hostname,
an exact matching Origin header, and a signed session token paired with an
HttpOnly SameSite=Strict cookie. The session expires after twelve hours and is
invalidated when the server restarts. Each explicit save obtains a fresh token;
no background process saves drafts or retries writes.

Class-scoped mapping snapshots are captured during preview ingestion. They are
separate from contextual snapshot paths, which can have a different parent.
The human endpoints resolve IDs against that prepared table and never trust
browser-supplied snapshots or review status. Review and correction append a fresh record with a declared `smat:supersedes`
extension pointing at the previous record. The original author, date, confidence,
method, rationale and snapshots remain structured fields on the original row.
A correction can change the predicate or retract/restore the correspondence.
Endpoints and snapshots stay fixed; another pair is a separate correspondence.
Only current records can be reviewed, with the check performed under the store
lock. Concurrent or stale second reviews return a conflict. Histories cannot
contain missing predecessors, forks or cycles. The file retains every record;
the mappings API and UI show only current records, including current rejections.

Automated suggestions cannot supersede records. Automated rejection refuses
anything except a current suggestion, so it cannot undo a human decision.
The codec accepts legacy files without the optional supersession column and
checks namespace expansions used by rows and definitions used by columns,
allowing compatible additions to the application or file metadata.


Draft endpoints remain fixed until the user explicitly chooses another pair or
reverses direction. Pane navigation does not silently change a draft. A draft
is held in Redux, shows Unsaved changes, and installs a page-exit warning.
Failed writes preserve it; the operator may retry or explicitly discard it.

This implements a trusted local operator workflow, not authentication or proof
of physical human presence. Remote writes are refused. No matcher or LLM is
imported by the web modules. Graph overlays remain outside Card 12; element-list
indicators and the shared mapping list show correspondence status.
