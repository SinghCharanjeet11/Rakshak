"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";
import Image from "next/image";
import { ThemeToggle } from "./ThemeToggle";

/** Inline so the whole icon set costs ~1KB instead of an icon package. */
const ICONS: Record<string, JSX.Element> = {
  dashboard: (
    <>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </>
  ),
  verify: (
    <>
      <path d="M12 3l7 3v6c0 4.5-3 8-7 9-4-1-7-4.5-7-9V6l7-3z" />
      <path d="M9 12l2 2 4-4" />
    </>
  ),
  rules: (
    <>
      <path d="M5 4h11l3 3v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z" />
      <path d="M8 10h8M8 14h8M8 18h5" />
    </>
  ),
};

const NAV = [
  { href: "/", label: "Dashboard", icon: "dashboard" },
  { href: "/verify", label: "Verify", icon: "verify" },
  { href: "/rules", label: "Rule-pack", icon: "rules" },
];

function Icon({ name }: { name: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4 shrink-0"
      aria-hidden
    >
      {ICONS[name]}
    </svg>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [pack, setPack] = useState<{
    rules: number;
    unverified: number;
    circularStale: boolean;
    circularAge: number | null;
  } | null>(null);

  useEffect(() => {
    getHealth()
      .then((h) =>
        setPack({
          rules: h.rules_loaded,
          unverified: h.unverified_rule_values.length,
          circularStale: h.circular_check_stale,
          circularAge: h.circular_check_age_days,
        }),
      )
      .catch(() => setPack(null));
  }, []);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <div className="relative flex min-h-screen">
      {/* Depth-0 atmosphere. Decorative only, so aria-hidden and pointer-events:none. */}
      <div className="atmosphere no-print" aria-hidden />

      {/* Sidebar — collapses to a top strip below lg */}
      <aside className="no-print sticky top-0 z-20 hidden h-screen w-56 shrink-0 flex-col border-r border-line bg-surface lg:flex">
        {/* The supplied lockup already contains the wordmark and tagline, so the sidebar
            draws no text of its own here — repeating it in Raleway would say it twice.
            The container takes the logo's own ground colour so there is no visible seam. */}
        {/* h-16 here and min-h-16 on the top bar: the two bottom borders have to land on
            the same y, or they read as a broken seam across the top of the app. */}
        <div
          className="flex h-16 items-center border-b border-line px-4"
          style={{ background: "var(--logo-bg)" }}
        >
          <Link href="/" className="flex w-full items-center">
            <Image
              src="/logo-side-light.png"
              alt="Rakshak — compliance for AI payment agents"
              width={620}
              height={226}
              priority
              className="logo-light h-11 w-auto"
            />
            <Image
              src="/logo-side-dark.png"
              alt="Rakshak — compliance for AI payment agents"
              width={620}
              height={226}
              priority
              className="logo-dark h-11 w-auto"
            />
          </Link>
        </div>

        <nav aria-label="Main" className="flex-1 space-y-0.5 p-3">
          {NAV.map((item) => {
            const active = isActive(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`group relative flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors ${
                  active ? "font-medium text-body" : "text-muted hover:text-body"
                }`}
              >
                {/* One element that travels between items rather than three that
                    cross-fade — the eye follows the move and learns the relationship. */}
                {active && (
                  <motion.span
                    layoutId="nav-active"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                    className="absolute inset-0 rounded-md bg-surface-2"
                    style={{ boxShadow: "inset 2px 0 0 var(--brand)" }}
                    aria-hidden
                  />
                )}
                <span className="relative z-10 flex items-center gap-2.5 transition-transform duration-150 group-hover:translate-x-0.5">
                  <Icon name={item.icon} />
                  {item.label}
                </span>
              </Link>
            );
          })}
        </nav>

        <div className="space-y-2 border-t border-line p-3">
          {pack && (
            <Link
              href="/rules"
              className="card-interactive block rounded-md border border-line px-2.5 py-2"
            >
              <span className="label">Rule-pack</span>
              <span className="mt-0.5 block text-xs text-body">
                {pack.rules} rules active
              </span>
              {pack.unverified > 0 && (
                <span className="mt-1 inline-flex items-center gap-1 rounded border border-warn-border bg-warn-bg px-1.5 py-0.5 text-[10px] font-medium text-warn-fg">
                  {pack.unverified} unverified
                </span>
              )}
              {/* A stale currency check is a distinct risk from an unverified value: the
                  number may be right and the circular still repealed underneath it. */}
              {pack.circularStale && (
                <span
                  title="The cited circular has not been confirmed current recently. Run scripts/check_circulars.py"
                  className="mt-1 inline-flex items-center gap-1 rounded border border-warn-border bg-warn-bg px-1.5 py-0.5 text-[10px] font-medium text-warn-fg"
                >
                  circular unchecked
                  {pack.circularAge !== null && ` ${pack.circularAge}d`}
                </span>
              )}
            </Link>
          )}
          <p className="px-1 text-[10px] leading-relaxed text-faint">
            Report-only. Never executes, blocks, or reverses a payment.
          </p>
        </div>
      </aside>

      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        {/* Mobile / narrow header */}
        <header className="safe-x safe-top no-print sticky top-0 z-30 flex min-h-16 items-center gap-4 border-b border-line bg-surface/90 backdrop-blur lg:justify-end lg:pt-0">
          <Link href="/" className="flex items-center lg:hidden">
            <span
              className="inline-flex items-center rounded px-1.5 py-1"
              style={{ background: "var(--logo-bg)" }}
            >
              <Image
                src="/logo-side-light.png"
                alt="Rakshak"
                width={620}
                height={226}
                className="logo-light h-6 w-auto"
              />
              <Image
                src="/logo-side-dark.png"
                alt="Rakshak"
                width={620}
                height={226}
                className="logo-dark h-6 w-auto"
              />
            </span>
          </Link>
          <nav aria-label="Main" className="scroll-x flex gap-1 text-sm lg:hidden">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive(item.href) ? "page" : undefined}
                className={`rounded px-2 py-1 ${
                  isActive(item.href)
                    ? "bg-surface-2 font-medium text-body"
                    : "text-muted"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 lg:ml-0">
            <ThemeToggle />
          </div>
        </header>

        <main id="main" className="safe-x safe-bottom relative z-10 mx-auto w-full max-w-[1400px] flex-1 py-6 lg:px-8">
          {children}
        </main>
      </div>
    </div>
  );
}
