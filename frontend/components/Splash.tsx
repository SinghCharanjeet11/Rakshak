"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

/**
 * Splash on full page load.
 *
 * Rendered **visible in the server HTML** and hidden by an effect, rather than the other way
 * round. Mounting it hidden and revealing it on the client would flash the dashboard for a
 * frame before the splash covered it, which is worse than no splash at all.
 *
 * It lives in the root layout, so it mounts once per real page load and does **not** re-fire
 * on client-side navigation between /verify, /reports and /rules — a splash between tabs
 * would be an obstacle, not an entrance.
 *
 * The overlay is removed from the DOM once faded, so it can never swallow a click or trap
 * focus. It is `aria-hidden` throughout: it carries no information a screen reader needs,
 * and the page behind it is already announced.
 */

const HOLD_MS = 900; // how long the mark sits before it starts to leave
const FADE_MS = 420;

export function Splash() {
  const [leaving, setLeaving] = useState(false);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      // No theatre for anyone who asked not to have it — just get out of the way.
      setGone(true);
      return;
    }
    const t1 = setTimeout(() => setLeaving(true), HOLD_MS);
    const t2 = setTimeout(() => setGone(true), HOLD_MS + FADE_MS);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, []);

  if (gone) return null;

  return (
    <div
      aria-hidden
      data-splash
      className="fixed inset-0 z-[100] flex items-center justify-center"
      style={{
        background: "#010206", // the square lockup's own ground, measured
        opacity: leaving ? 0 : 1,
        transition: `opacity ${FADE_MS}ms ease-out`,
        pointerEvents: leaving ? "none" : "auto",
      }}
    >
      <Image
        src="/splash-logo.png"
        alt=""
        width={600}
        height={600}
        priority
        className="w-40 max-w-[45vw] animate-[splash-in_600ms_ease-out_both] sm:w-52"
      />
    </div>
  );
}
