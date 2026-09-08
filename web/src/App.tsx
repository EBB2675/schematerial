import { useEffect } from "react";

import { useCatalogueQuery } from "./api";
import { AlignerToolbar } from "./components/AlignerToolbar";
import { PairBar } from "./components/PairBar";
import { SchemaPane } from "./components/SchemaPane";
import { useAppDispatch, useAppSelector } from "./store";
import { focusSide, open as openPair, setExpanded } from "./uiSlice";

const TEXT_INPUTS = new Set(["text", "search", "url", "email", "password", "tel", "number"]);

/** Whether a bracket typed here is a character rather than a command. */
function takesTypedText(node: EventTarget | null): boolean {
  if (!(node instanceof HTMLElement)) return false;
  if (node.isContentEditable || node.tagName === "TEXTAREA" || node.tagName === "SELECT") {
    return true;
  }
  return node instanceof HTMLInputElement && TEXT_INPUTS.has(node.type);
}

/**
 * The aligner: two schemas side by side, read only.
 *
 * There is one interface, not a browsing mode and a comparing mode. Closing one
 * side gives back a single full-width schema, which is the same components with
 * one pane hidden rather than a second page to keep working.
 */
export function App() {
  const dispatch = useAppDispatch();
  const opened = useAppSelector((state) => state.ui.opened);
  const expanded = useAppSelector((state) => state.ui.expanded);
  const { data, isLoading, isError } = useCatalogueQuery();
  const schemas = data?.schemas ?? [];

  useEffect(() => {
    if (opened || schemas.length === 0) return;
    dispatch(openPair(schemas));
  }, [opened, schemas, dispatch]);

  // `[` and `]` move the keyboard between the sides -- except where they are
  // characters the user is typing, which is a text field and nothing else. A
  // checkbox or a button is not text entry, so the switch still works there.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (takesTypedText(event.target)) return;
      if (event.key === "[") dispatch(focusSide("left"));
      else if (event.key === "]") dispatch(focusSide("right"));
      else if (event.key === "Escape") dispatch(setExpanded(null));
      else return;
      event.preventDefault();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [dispatch]);

  if (isLoading) return <p className="notice">Loading the schema catalogue…</p>;
  if (isError) return <p className="notice error">The preview server did not answer.</p>;
  if (schemas.length === 0) {
    return <p className="notice error">The server started with no schemas.</p>;
  }

  return (
    <div className="app">
      <AlignerToolbar schemas={schemas} />
      <main className={`panes${expanded === null ? "" : " single"}`}>
        {(expanded === null || expanded === "left") && (
          <SchemaPane side="left" schemas={schemas} />
        )}
        {(expanded === null || expanded === "right") && (
          <SchemaPane side="right" schemas={schemas} />
        )}
      </main>
      <PairBar />
    </div>
  );
}
