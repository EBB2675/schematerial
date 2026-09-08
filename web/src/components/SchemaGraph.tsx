import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, type KeyboardEvent } from "react";

import { useElementsQuery, useGraphQuery } from "../api";
import { sideLabel, type Side } from "../panes";
import { filterElements, type Filters } from "../search";
import { useAppDispatch, useAppSelector } from "../store";
import type { GraphEdge, GraphNode, IndexRow } from "../types";
import { activate, filtersOf, selectElement } from "../uiSlice";

/**
 * One schema's classes and the structure between them.
 *
 * Positions arrive from the server, laid out once when the document was
 * ingested. Nothing here computes a layout, so selecting, hovering, panning or
 * searching cannot move a box: the same class is in the same place for as long
 * as the schema is on screen, and in the same place again after a restart.
 *
 * The search highlights rather than filters. Dropping a class because its name
 * does not match would silently cut the edges that run through it, and the
 * structure below would look like something it is not.
 */

// The class box's own size. It has to fit inside the COLUMN and ROW spacing the
// server lays out with, and it is declared here rather than measured so an edge
// is drawn in the right place on the first frame instead of after a measure
// pass that would move it.
const NODE_WIDTH = 180;
const NODE_HEIGHT = 36;

/** A class is dimmed, not removed, when the current search does not reach it. */
function highlighted(nodes: GraphNode[], rows: readonly IndexRow[], filters: Filters): Set<string> {
  if (filters.query.trim() === "" && filters.kind === "all") {
    return new Set(nodes.map((node) => node.id));
  }
  // Reuse the list's own matching so the two views agree on what a search means.
  const matched = new Set(
    filterElements(rows, { ...filters, kind: "all" }).map((row) => row.id),
  );
  const reached = new Set<string>();
  for (const node of nodes) {
    if (matched.has(node.id)) reached.add(node.id);
  }
  // A class whose attribute matched is reached too, which is what makes
  // searching for a unit or a range useful on a graph of classes.
  for (const row of rows) {
    if (row.kind === "attribute" && matched.has(row.id)) reached.add(row.class_id);
  }
  return reached;
}

function toNodes(
  nodes: GraphNode[],
  selected: string | null,
  lit: Set<string>,
): Node<Record<string, unknown>>[] {
  return nodes.map((node) => ({
    id: node.id,
    position: { x: node.x, y: node.y },
    data: { label: node.name },
    selected: node.id === selected,
    draggable: false,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    measured: { width: NODE_WIDTH, height: NODE_HEIGHT },
    className: [
      "class-node",
      lit.has(node.id) ? "lit" : "dimmed",
      node.diagnostics > 0 ? "warned" : "",
    ]
      .filter(Boolean)
      .join(" "),
  }));
}

function toEdges(edges: GraphEdge[]): Edge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    className: `structural ${edge.kind}`,
    // A mixin is a real distinction, not decoration: the conversion made the
    // first source base the backbone and every later one a mixin.
    animated: false,
    label: edge.label ?? undefined,
  }));
}

function Canvas({ side, schema }: { side: Side; schema: string }) {
  const dispatch = useAppDispatch();
  const selected = useAppSelector((state) => state.ui.panes[side].selected);
  const filters = useAppSelector((state) => filtersOf(state.ui, side));
  const isActive = useAppSelector((state) => state.ui.active === side);
  const expanded = useAppSelector((state) => state.ui.expanded);
  const focusRequests = useAppSelector((state) => state.ui.focusRequests);
  const { data, isLoading, isError } = useGraphQuery(schema);
  // The same index the list uses, from the same cache entry: highlighting a
  // class because one of its attributes matched needs the attribute rows.
  const { data: index } = useElementsQuery(schema);

  const graphNodes = data?.nodes;
  const graphEdges = data?.edges;
  const lit = useMemo(
    () => highlighted(graphNodes ?? [], index?.elements ?? [], filters),
    [graphNodes, index, filters],
  );
  const nodes = useMemo(
    () => toNodes(graphNodes ?? [], selected, lit),
    [graphNodes, selected, lit],
  );
  const edges = useMemo(() => toEdges(graphEdges ?? []), [graphEdges]);

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    dispatch(activate(side));
    dispatch(selectElement({ side, id: node.id }));
  };

  // The graph answers the same keys the list does, so switching a side between
  // the two views does not take the keyboard away from it.
  const flow = useReactFlow();
  const canvas = useRef<HTMLDivElement>(null);
  const lastRequest = useRef(focusRequests);
  useEffect(() => {
    if (lastRequest.current === focusRequests) return;
    lastRequest.current = focusRequests;
    if (isActive) canvas.current?.focus();
  }, [focusRequests, isActive]);

  // Giving the side the window, or handing it back, changes how much canvas
  // there is. Refit so the graph uses it; the boxes keep their positions and
  // only the camera moves.
  const settled = useRef(false);
  useEffect(() => {
    if (!settled.current) {
      settled.current = true;
      return;
    }
    const frame = requestAnimationFrame(() => flow.fitView({ padding: 0.08 }));
    return () => cancelAnimationFrame(frame);
  }, [expanded, flow]);

  const move = useCallback(
    (delta: number) => {
      const all = graphNodes ?? [];
      if (all.length === 0) return;
      const current = all.findIndex((node) => node.id === selected);
      const base = current < 0 ? (delta > 0 ? -1 : 0) : current;
      const next = Math.min(Math.max(base + delta, 0), all.length - 1);
      const node = all[next];
      if (node === undefined) return;
      dispatch(selectElement({ side, id: node.id }));
      // Moving the viewport to the selected class is not a relayout: the class
      // keeps the position it was given at ingestion.
      flow.setCenter(node.x, node.y, { zoom: flow.getZoom(), duration: 0 });
    },
    [graphNodes, selected, dispatch, side, flow],
  );

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    switch (event.key) {
      case "ArrowDown":
      case "ArrowRight":
        move(1);
        break;
      case "ArrowUp":
      case "ArrowLeft":
        move(-1);
        break;
      case "PageDown":
        move(10);
        break;
      case "PageUp":
        move(-10);
        break;
      case "Home":
        move(-(graphNodes ?? []).length);
        break;
      case "End":
        move((graphNodes ?? []).length);
        break;
      default:
        return;
    }
    event.preventDefault();
  };

  if (isLoading) return <p className="count-line subtle">laying out the class graph…</p>;
  if (isError || data === undefined) {
    return <p className="count-line subtle">the class graph could not be loaded</p>;
  }

  return (
    <div className="graph" aria-label={`class graph of ${schema} on the ${sideLabel(side)}`}>
      <p className="count-line subtle">
        {data.nodes.length} classes · {data.edges.length} structural edges · positions fixed
        at load
      </p>
      <div
        className="canvas"
        ref={canvas}
        tabIndex={0}
        role="application"
        aria-label={`class graph of ${schema}, ${sideLabel(side)} side`}
        onKeyDown={onKeyDown}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodeClick={onNodeClick}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable
          fitView
          fitViewOptions={{ padding: 0.08 }}
          minZoom={0.05}
          proOptions={{ hideAttribution: true }}
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
    </div>
  );
}

export function SchemaGraph({ side, schema }: { side: Side; schema: string }) {
  return (
    <ReactFlowProvider>
      <Canvas side={side} schema={schema} />
    </ReactFlowProvider>
  );
}
