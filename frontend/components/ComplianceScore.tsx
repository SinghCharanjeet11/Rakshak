"use client";

import { animate, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";
import { CopyButton } from "./ui";
import type { Report, Severity } from "@/lib/api";

const ORDER: Severity[] = ["critical", "high", "medium", "low"];
const DOT: Record<Severity, string> = {
  critical: "bg-sev-critical",
  high: "bg-sev-high",
  medium: "bg-sev-medium",
  low: "bg-sev-low",
};

/**
 * The headline (04-frontend.md §2). First thing on the report and the thing you point at
 * in the demo, so it carries the score, the split, the severity mix and the provenance —
 * enough to judge the batch without scrolling.
 */
export function ComplianceScore({ report }: { report: Report }) {
  const reduced = useReducedMotion();

  // The number counts up with the ring rather than snapping — the two are the same
  // fact, and having them disagree for 700ms looks like a glitch.
  const [shown, setShown] = useState(reduced ? report.score : 0);
  useEffect(() => {
    if (reduced) {
      setShown(report.score);
      return;
    }
    const controls = animate(0, report.score, {
      duration: 0.7,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: setShown,
    });
    return () => controls.stop();
  }, [report.score, reduced]);

  const counts = ORDER.map((sev) => ({
    sev,
    n: report.violations.filter((v) => v.severity === sev).length,
  })).filter((c) => c.n > 0);

  const clean = report.failed === 0;
  const exemptCount = new Set(report.exemptions_applied.map((e) => e.action_id)).size;

  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(100, report.score)) / 100;

  return (
    <section className="card reveal p-6" aria-label="Compliance score">
      <div className="flex flex-col gap-6 sm:flex-row sm:items-start">
        <div className="relative h-28 w-28 shrink-0">
          <svg viewBox="0 0 100 100" className="h-28 w-28 -rotate-90" aria-hidden>
            <circle
              cx="50"
              cy="50"
              r={radius}
              fill="none"
              strokeWidth="8"
              className="stroke-track"
            />
            <motion.circle
              cx="50"
              cy="50"
              r={radius}
              fill="none"
              strokeWidth="8"
              strokeLinecap="round"
              className={clean ? "stroke-pass-fg" : "stroke-fail-fg"}
              strokeDasharray={circumference}
              initial={{
                strokeDashoffset: reduced
                  ? circumference * (1 - pct)
                  : circumference,
              }}
              animate={{ strokeDashoffset: circumference * (1 - pct) }}
              transition={{ duration: reduced ? 0 : 0.7, ease: "easeOut" }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span
              className="text-2xl font-semibold tabular-nums tracking-tight"
              style={{
                color: clean ? "var(--pass-fg)" : "var(--fail-fg)",
                textShadow: `0 0 22px ${clean ? "var(--brand-glow)" : "var(--fail-glow)"}`,
              }}
            >
              {shown.toFixed(1)}
            </span>
            <span className="text-[10px] uppercase tracking-wider text-faint">
              / 100
            </span>
          </div>
          <span className="sr-only">
            Compliance score {report.score.toFixed(1)} out of 100.
          </span>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="pop rounded-md border border-pass-border bg-pass-bg px-2 py-0.5 text-sm font-medium tabular-nums text-pass-fg">
              {report.passed} pass
            </span>
            <span className="pop d-1 rounded-md border border-fail-border bg-fail-bg px-2 py-0.5 text-sm font-medium tabular-nums text-fail-fg">
              {report.failed} fail
            </span>
            {exemptCount > 0 && (
              <span className="pop d-2 rounded-md border border-exempt-border bg-exempt-bg px-2 py-0.5 text-sm tabular-nums text-exempt-fg">
                {exemptCount} exempt
              </span>
            )}
            <span className="text-xs tabular-nums text-faint">
              {report.actions.length} actions checked
            </span>
          </div>

          {counts.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
              {counts.map(({ sev, n }) => (
                <span
                  key={sev}
                  className="inline-flex items-center gap-1.5 text-xs text-muted"
                >
                  <span className={`h-2 w-2 rounded-full ${DOT[sev]}`} aria-hidden />
                  {n} {sev}
                </span>
              ))}
            </div>
          )}

          <p className="mt-3 text-sm leading-relaxed text-body">{report.summary}</p>

          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-line pt-3 clause">
            <span>rule-pack {report.rulepack_version}</span>
            <span className="inline-flex items-center gap-0.5">
              {report.id}
              <CopyButton value={report.id} label="copy" />
            </span>
            {report.correlation_id && <span>corr {report.correlation_id}</span>}
          </div>
        </div>
      </div>
    </section>
  );
}
