import { useEffect } from "react";

import { useCatalogueQuery } from "./api";
import { AppBar } from "./components/AppBar";
import { AuthoringDrawer } from "./components/AuthoringDrawer";
import { MappingsView } from "./components/MappingsView";
import { PmdcoPanel } from "./components/PmdcoPanel";
import { SchemaPane } from "./components/SchemaPane";
import { SelectionStrip } from "./components/SelectionStrip";
import { useAppDispatch, useAppSelector } from "./store";
import {
  focusSide,
  open as openPair,
  setAuthoring,
  setExpanded,
  setPmdco,
} from "./uiSlice";

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
 * The workspace: two schemas side by side, with authoring and review reachable
 * from them.
 *
 * There is one interface, not a browsing mode and a comparing mode. Closing one
 * side gives back a single full-width schema, which is the same components with
 * one pane hidden rather than a second page to keep working. Authoring, the
 * PMDco taxonomy and the saved crosswalk are all opened on demand, so the two
 * panes keep the window unless something is being written.
 */
export function App() {
  const dispatch = useAppDispatch();
  const opened = useAppSelector((state) => state.ui.opened);
  const expanded = useAppSelector((state) => state.ui.expanded);
  const workspace = useAppSelector((state) => state.ui.workspace);
  const pmdco = useAppSelector((state) => state.ui.pmdco);
  const authoring = useAppSelector((state) => state.ui.authoring);
  const dirty = useAppSelector((state) => state.authoring.dirty);
  const { data, isLoading, isError } = useCatalogueQuery();
  const schemas = data?.schemas ?? [];

  useEffect(() => {
    if (opened || schemas.length === 0) return;
    dispatch(openPair(schemas));
  }, [opened, schemas, dispatch]);

  // A draft is the only unsaved state in the interface, and it outlives the
  // drawer being closed. The browser's own warning is the last guard on it.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // A popover is closed by pointing away from it, the way every other popover
  // behaves. `<details>` gives keyboard and screen-reader behaviour for free but
  // has no light dismiss of its own, and one left open covers the list.
  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      const target = event.target;
      for (const panel of document.querySelectorAll<HTMLDetailsElement>("details.disclosure[open]")) {
        if (target instanceof Node && panel.contains(target)) continue;
        panel.open = false;
      }
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);

  // `[` and `]` move the keyboard between the sides -- except where they are
  // characters the user is typing, which is a text field and nothing else. A
  // checkbox or a button is not text entry, so the switch still works there.
  // Escape closes whatever is on top, innermost first, and never discards a
  // draft: closing the drawer keeps everything typed into it.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "Escape") {
        const popover = document.querySelector<HTMLDetailsElement>("details.disclosure[open]");
        if (popover !== null) popover.open = false;
        else if (authoring) dispatch(setAuthoring(false));
        else if (pmdco) dispatch(setPmdco(false));
        else dispatch(setExpanded(null));
        event.preventDefault();
        return;
      }
      if (takesTypedText(event.target)) return;
      if (event.key === "[") dispatch(focusSide("left"));
      else if (event.key === "]") dispatch(focusSide("right"));
      else if (event.key === "/") {
        const search = document.querySelector<HTMLInputElement>("input[aria-label='shared search']");
        if (search === null) return;
        search.focus();
        search.select();
      } else return;
      event.preventDefault();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [dispatch, authoring, pmdco]);

  if (isLoading) return <p className="notice">Loading the schema catalogue…</p>;
  if (isError) return <p className="notice error">The preview server did not answer.</p>;
  if (schemas.length === 0) {
    return <p className="notice error">The server started with no schemas.</p>;
  }

  return (
    <div className={`app${authoring ? " drawer-open" : ""}`}>
      <AppBar schemas={schemas} />
      {workspace === "align" ? (
        <div className="workspace" id="workspace-align" role="tabpanel" aria-labelledby="tab-align">
          <div className="workspace-main">
            <main className={`panes${expanded === null ? "" : " single"}`}>
              {(expanded === null || expanded === "left") && (
                <SchemaPane side="left" schemas={schemas} />
              )}
              {(expanded === null || expanded === "right") && (
                <SchemaPane side="right" schemas={schemas} />
              )}
            </main>
            <SelectionStrip />
          </div>
          <PmdcoPanel />
        </div>
      ) : (
        <div
          className="workspace"
          id="workspace-mappings"
          role="tabpanel"
          aria-labelledby="tab-mappings"
        >
          <MappingsView />
        </div>
      )}
      <AuthoringDrawer />
    </div>
  );
}
