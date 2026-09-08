import { useEffect, useState } from "react";

type Theme = "system" | "light" | "dark";

const ORDER: Theme[] = ["system", "light", "dark"];
const KEY = "schematerial-theme";

function stored(): Theme {
  try {
    const value = window.localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    // Private browsing and blocked site data both throw here; the operating
    // system's own preference is a perfectly good answer.
    return "system";
  }
}

/**
 * Which of the two themes the page is painted in.
 *
 * The default follows the operating system, which is the right answer for
 * almost everyone. The override exists because this interface is read for long
 * stretches next to a terminal or a source editor that may not agree with it.
 */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(stored);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    try {
      if (theme === "system") window.localStorage.removeItem(KEY);
      else window.localStorage.setItem(KEY, theme);
    } catch {
      // Not persisting a preference is a smaller failure than not applying it.
    }
  }, [theme]);

  const next = ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length] ?? "system";
  return (
    <button
      type="button"
      className="toggle"
      aria-label={`theme: ${theme}; switch to ${next}`}
      title={`Theme: ${theme}`}
      onClick={() => setTheme(next)}
    >
      {theme === "dark" ? "dark" : theme === "light" ? "light" : "auto"}
    </button>
  );
}
