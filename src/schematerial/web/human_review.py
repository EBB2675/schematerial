"""Loopback-only human review routes. Never imported by suggestion producers."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from schematerial.identity import ElementSnapshot
from schematerial.mappings.store import MappingRow, MappingStore, reference
from schematerial.web.preview import SchemaPreview

COOKIE = "schematerial_review"
LOCAL = {"localhost", "127.0.0.1", "::1"}
TTL = 12 * 60 * 60


def install_review(
    app: FastAPI, previews: Sequence[SchemaPreview], store: MappingStore, *,
    extra_snapshots: Mapping[tuple[str, str], ElementSnapshot] | None = None,
) -> None:
    """Install the human boundary over prepared snapshots, with no materialisation."""
    snapshots = {
        (preview.name, identifier): detail["mapping_snapshot"]
        for preview in previews for identifier, detail in preview.details.items()
        if "mapping_snapshot" in detail
    }
    for key, value in (extra_snapshots or {}).items():
        if key in snapshots:
            raise ValueError(f"Duplicate mapping snapshot: {key}")
        snapshots[key] = value.model_dump()
    secret = secrets.token_bytes(32)

    def local(request: Request) -> None:
        if (request.client is None or request.client.host not in LOCAL
                or request.url.hostname not in LOCAL):
            raise HTTPException(403, "Manual review is available only on loopback")
        if request.headers.get("sec-fetch-site") not in (None, "same-origin", "none"):
            raise HTTPException(403, "Cross-origin review is forbidden")

    def signature(cookie: str) -> str:
        return hmac.new(secret, cookie.encode(), hashlib.sha256).hexdigest()

    def authorize(request: Request) -> None:
        local(request)
        origin = f"{request.url.scheme}://{request.url.netloc}"
        if request.headers.get("origin") != origin:
            raise HTTPException(403, "A same-origin review submission is required")
        cookie = request.cookies.get(COOKIE, "")
        token = request.headers.get("x-review-token", "")
        try:
            issued = int(cookie.rsplit(".", 1)[1])
        except (ValueError, IndexError):
            raise HTTPException(403, "Open a review session first") from None
        if (not 0 <= time.time() - issued <= TTL
                or not hmac.compare_digest(token.encode(), signature(cookie).encode())):
            raise HTTPException(403, "Review session expired; reopen the review session")

    @app.get("/api/review-session")
    def review_session(request: Request) -> JSONResponse:
        local(request)
        cookie = request.cookies.get(COOKIE)
        try:
            valid = cookie is not None and 0 <= time.time() - int(cookie.rsplit(".", 1)[1]) <= TTL
        except (ValueError, IndexError):
            valid = False
        if not valid or cookie is None:
            cookie = f"{secrets.token_urlsafe(32)}.{int(time.time())}"
        response = JSONResponse({"token": signature(cookie)}, headers={"Cache-Control": "no-store"})
        response.set_cookie(COOKIE, cookie, httponly=True, samesite="strict", max_age=TTL,
                            secure=request.url.scheme == "https", path="/api")
        return response

    @app.get("/api/mappings")
    def mappings() -> JSONResponse:
        return JSONResponse({"rows": [row.model_dump(mode="json") for row in store.rows()]},
                            headers={"Cache-Control": "no-store"})

    def fields(payload: dict[str, Any], expected: set[str]) -> None:
        if set(payload) != expected:
            raise HTTPException(422, "Missing or unexpected form fields")

    def snapshot(schema: str, identifier: str) -> Any:
        result = snapshots.get((schema, identifier))
        if result is None:
            raise HTTPException(422, f"Unknown mapping element: {schema} / {identifier}")
        return result

    @app.post("/api/human/mappings")
    def create_manual(request: Request, payload: dict[str, Any]) -> JSONResponse:
        authorize(request)
        fields(payload, {"subject_schema", "subject_id", "object_schema", "object_id",
                         "predicate_id", "author_id", "comment", "confidence"})
        try:
            row = MappingRow.model_validate({
                **{k: v for k, v in payload.items() if not k.endswith("_schema")},
                "subject_snapshot": snapshot(payload["subject_schema"], payload["subject_id"]),
                "object_snapshot": snapshot(payload["object_schema"], payload["object_id"]),
                "mapping_justification": "semapv:ManualMappingCuration",
                "review_status": "accepted",
            })
        except (ValidationError, TypeError) as error:
            raise HTTPException(422, str(error)) from error

        def create(rows: list[MappingRow]) -> MappingRow:
            triple = (row.subject_id, row.predicate_id, row.object_id)
            if any((r.subject_id, r.predicate_id, r.object_id) == triple for r in rows):
                raise HTTPException(
                    409, "Correspondence already exists; reload mappings and inspect the saved row"
                )
            rows.append(row)
            return row
        try:
            saved = store._transaction(create)
        except OSError as error:
            raise HTTPException(503, "Save failed; your draft is still unsaved") from error
        return JSONResponse(saved.model_dump(mode="json"), status_code=201)

    @app.post("/api/human/review")
    def review_manual(request: Request, payload: dict[str, Any]) -> JSONResponse:
        authorize(request)
        fields(payload, {"record_id", "action", "author_id", "comment"})
        if payload["action"] not in ("accept", "reject"):
            raise HTTPException(422, "Choose accept or reject")
        try:
            reference(payload["author_id"])
            if not isinstance(payload["comment"], str) or not payload["comment"].strip():
                raise ValueError("Review justification is required")
        except (ValueError, TypeError) as error:
            raise HTTPException(422, str(error)) from error

        def review(rows: list[MappingRow]) -> MappingRow:
            for i, row in enumerate(rows):
                if row.record_id != payload["record_id"]:
                    continue
                if row.review_status != "suggested":
                    raise HTTPException(409, "This row has already been reviewed; reload mappings")
                result = MappingRow.model_validate({
                    **row.model_dump(),
                    "review_status": "accepted" if payload["action"] == "accept" else "rejected",
                    "author_id": payload["author_id"], "mapping_date": date.today(),
                    "mapping_justification": "semapv:ManualMappingCuration",
                    "comment": f"{payload['comment']}\n\nOriginal suggestion by {row.author_id} "
                               f"({row.mapping_justification}): {row.comment}",
                })
                rows[i] = result
                return result
            raise HTTPException(404, "Unknown mapping record")
        try:
            saved = store._transaction(review)
        except OSError as error:
            raise HTTPException(503, "Review could not be saved; retry explicitly") from error
        return JSONResponse(saved.model_dump(mode="json"))
