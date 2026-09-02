"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";

const NEXT: Record<Theme, Theme> = {
  system: "light",
  light: "dark",
  dark: "system",
};
const GLYPH: Record<Theme, string> = { system: "◐", light: "☀", dark: "☾" };

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    setTheme((localStorage.getItem("rakshak-theme") as Theme) ?? "system");
  }, []);

  const apply = (next: Theme) => {
    setTheme(next);
    try {
      localStorage.setItem("rakshak-theme", next);
    } catch {
      /* private mode — the choice just will not persist */
    }
    const root = document.documentElement;
    if (next === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", next);
  };

  // Render a placeholder until mounted so server and client markup agree.
  if (!mounted) return <span className="h-7 w-7" aria-hidden />;

  return (
    <button
      type="button"
      onClick={() => apply(NEXT[theme])}
      className="rounded-md border border-line px-2 py-1 text-xs text-muted transition-colors hover:bg-surface-2 hover:text-body"
      aria-label={`Theme: ${theme}. Switch to ${NEXT[theme]}.`}
      title={`Theme: ${theme}`}
    >
      <span aria-hidden>{GLYPH[theme]}</span>
    </button>
  );
}
