import { useEffect, useRef, useState } from "react";

/**
 * A stable identifier, shown as itself and copyable in one action.
 *
 * Identifiers are what the crosswalk is written in, so they are never
 * paraphrased or shortened away here; they are simply no longer the first thing
 * a reader's eye lands on. Copying is offered because retyping a percent-escaped
 * CURIE by hand is how a wrong row gets written.
 */
export function Copyable({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timer.current !== null) clearTimeout(timer.current);
  }, []);

  function copy() {
    // Absent in a plain HTTP context and in a test environment; the identifier
    // stays selectable either way, so the button simply does nothing visible.
    const clipboard = navigator.clipboard;
    if (clipboard?.writeText === undefined) return;
    void clipboard.writeText(value).then(
      () => {
        setCopied(true);
        if (timer.current !== null) clearTimeout(timer.current);
        timer.current = setTimeout(() => setCopied(false), 1200);
      },
      () => undefined,
    );
  }

  return (
    <button
      type="button"
      className={`copy${copied ? " copied" : ""}`}
      aria-label={`copy ${label}`}
      title={copied ? "Copied" : `Copy ${label}`}
      onClick={copy}
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}
