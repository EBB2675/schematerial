# Manual crosswalk authoring (Card 12)

Build the frontend with `cd web && npm run build`. From the repository root:

```sh
uv run schematerial-web \
  runs/extraction/nomad-simulations-0.6.0-model_method-v1.1.json \
  runs/extraction/bam-masterdata-0.13.1-object_types-v1.2.json \
  --mappings runs/crosswalk.sssom.tsv
```

Open the loopback address printed by the server. Choose an element in each
pane, then **Use selected pair**. The left element starts as subject and the
right as object. **Reverse direction** reverses those endpoints without
changing the predicate. The form always displays subject → predicate → object.
For `narrowMatch`, the object is narrower than the subject; for `broadMatch`,
the object is broader than the subject.

Enter an author URI (for example an ORCID URL), confidence, and written
justification. **Save accepted mapping** records the explicit human action.
The semantic justification is `semapv:ManualMappingCuration`; the written
reason is preserved in SSSOM's `comment`. A low confidence does not prevent a
human accepting a row, and a high confidence never makes a tool accept one.

The form says **Unsaved changes** until saving succeeds or the draft is
explicitly discarded. Pane browsing does not change its endpoints. Failed
saves retain the draft and show an error. Leaving the page with an unsaved
draft triggers the browser's exit warning. Drafts are not persisted across
closing the browser; saved rows are persisted to the configured TSV file.

The mapping list shows direction, author, date, confidence, justification, and
review status. Suggested rows have a **Review suggestion** button. Supply a
reviewing author and rationale, then explicitly **Accept suggestion** or
**Reject suggestion**. A rejection remains a row and suppresses another
suggestion for the same ordered subject/predicate/object triple. The original
suggestion's author, method, and rationale remain in the comment after review.

List elements are marked mapped, suggested, or rejected. Where several rows
refer to an element, mapped takes display precedence over suggested and rejected;
the full mapping list retains every row. **Reload mappings** also picks up rows
written by another local process. Graph correspondence overlays are a later card.

There are no matcher or LLM dependencies in this workflow. Tests use inline
schemas and synthetic human-review requests, never expert ground truth. Real
schema smoke checks verified 455 NOMAD model-method elements and 1,212 BAM
object-type elements, each with a prepared mapping snapshot, plus the review
session, empty mapping store and built client. No real scientific mappings were
created by those smoke checks.

See decision 008 for the trusted-local-operator boundary and its limitations.


To fix a saved decision, choose **Correct mapping**, enter your author identity
and justification, and either change the predicate and **Save accepted correction**
or **Retract mapping**. A retracted mapping can be restored through the same form.
Each submission appends a new record linked by `smat:supersedes`; the TSV keeps
the complete structured history, while the interface shows only current records.
Reload after a conflict before making another correction.
