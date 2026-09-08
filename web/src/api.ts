/**
 * The preview API.
 *
 * Four read-only shapes: the schema catalogue, one schema's compact element
 * index, one element's detail, and one schema's structural graph. The index and
 * the graph are fetched once per schema and kept; detail is fetched per
 * selection. The graph carries its own laid-out positions, so nothing about it
 * is computed here.
 */

import { createApi, fetchBaseQuery } from "@reduxjs/toolkit/query/react";

import type { ElementDetail, IndexRow, SchemaGraph, SchemaSummary } from "./types";

export interface Catalogue {
  schemas: SchemaSummary[];
}

export interface ElementIndex {
  schema: string;
  elements: IndexRow[];
}

// Absolute, so the request URL is well-formed wherever the page is served from.
const API_BASE = new URL("/api/", window.location.origin).toString();

export const api = createApi({
  reducerPath: "api",
  baseQuery: fetchBaseQuery({ baseUrl: API_BASE }),
  // Schemas are ingested once at server startup and never change while it runs.
  keepUnusedDataFor: Number.POSITIVE_INFINITY,
  refetchOnFocus: false,
  refetchOnReconnect: false,
  endpoints: (build) => ({
    catalogue: build.query<Catalogue, void>({
      query: () => "schemas",
    }),
    elements: build.query<ElementIndex, string>({
      query: (schema) => `schemas/${encodeURIComponent(schema)}/elements`,
    }),
    graph: build.query<SchemaGraph, string>({
      query: (schema) => `schemas/${encodeURIComponent(schema)}/graph`,
    }),
    element: build.query<ElementDetail, { schema: string; id: string }>({
      // The identifier is a CURIE with a colon, dots and percent escapes; it
      // travels as a query parameter so it is encoded exactly once.
      query: ({ schema, id }) => ({
        url: `schemas/${encodeURIComponent(schema)}/element`,
        params: { id },
      }),
    }),
  }),
});

export const { useCatalogueQuery, useElementsQuery, useGraphQuery, useElementQuery } =
  api;
