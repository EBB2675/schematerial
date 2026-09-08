# Manual crosswalk authoring

Build the frontend with `cd web && npm run build`. From the repository root:

```sh
uv run schematerial-web \
  runs/extraction/nomad-simulations-0.6.0-model_method-v1.1.json \
  runs/extraction/bam-masterdata-0.13.1-object_types-v1.2.json \
  --mappings runs/crosswalk.sssom.tsv
```

Open the loopback address printed by the server. Choose an element in each
pane. The selection strip along the bottom names both, in the direction a
mapping would be written: subject on the left of the arrow, object on its
right. **swap** turns that round before any form is opened. **Create mapping**
opens the authoring drawer with those endpoints.

The drawer always displays subject → predicate → object, and **Reverse
direction** reverses the endpoints without changing the predicate. For
`narrowMatch`, the object is narrower than the subject; for `broadMatch`, the
object is broader than the subject. The drawer names what the chosen predicate
asserts, in words, above the fields.

Enter an author URI (for example an ORCID URL), confidence, and written
justification. **Save accepted mapping** records the explicit human action and
closes the drawer. The semantic justification is
`semapv:ManualMappingCuration`; the written reason is preserved in SSSOM's
`comment`. A low confidence does not prevent a human accepting a row, and a
high confidence never makes a tool accept one.

The bar at the top of the window says **Unsaved changes** until saving succeeds
or the draft is explicitly discarded, wherever you are in the interface. The
draft belongs to the session and not to the drawer: closing the drawer with
**close**, Escape or a click outside it keeps everything typed in, and
**Create mapping** reopens it unchanged. **Discard draft** asks first. Pane
browsing does not change a draft's endpoints. Failed saves retain the draft and
show the error. Leaving the page with an unsaved draft triggers the browser's
exit warning. Drafts are not persisted across closing the browser; saved rows
are persisted to the configured TSV file.

The **Mappings** view is a table of every current row: status, subject,
predicate, object, author, date, confidence and justification, filtered by
review status or by text. Both identifiers are shown in full and each has a
copy button. Suggested rows have a **Review suggestion** button, accepted rows
a **Correct mapping** button; either opens the same drawer. Supply a reviewing
author and rationale, then explicitly **Accept suggestion** or **Reject
suggestion**. A rejection remains a row and suppresses another suggestion for
the same ordered subject/predicate/object triple. The original suggestion's
author, method, and rationale remain in the comment after review.

List elements are marked mapped, suggested, or rejected. Where several rows
refer to an element, mapped takes display precedence over suggested and rejected;
the Mappings table retains every current row. **Reload mappings** also picks up
rows written by another local process. Graph correspondence overlays are a
later card.

There are no matcher or LLM dependencies in this workflow. Tests use inline
schemas and synthetic human-review requests, never expert ground truth. Real
schema smoke checks verified 455 NOMAD model-method elements and 1,212 BAM
object-type elements, each with a prepared mapping snapshot, plus the review
session, empty mapping store and built client. No real scientific mappings were
created by those smoke checks.

The review routes answer on loopback only, and only to same-origin submissions
carrying a session-bound token. They validate the submitted identifiers against
the prepared schema tables and capture the snapshots on the server, so a caller
cannot supply its own. This is a trusted-local-operator model, not an
authorisation system: it stops another website issuing writes, and it does not
authenticate a person against another process run by the same operator. Serving
writes beyond loopback would need an authentication and review-permission design
first.


To fix a saved decision, choose **Correct mapping** in the Mappings view, enter your author identity
and justification, and either change the predicate and **Save accepted correction**
or **Retract mapping**. A retracted mapping can be restored through the same form.
Each submission appends a new record linked by `smat:supersedes`; the TSV keeps
the complete structured history, while the interface shows only current records.
Reload after a conflict before making another correction.
