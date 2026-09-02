"use client";

import Link from "next/link";
import { formatIST, type ReportSummary } from "@/lib/api";

/**
 * One row in the recent-reports list.
 *
 * The previous version printed each report's full prose summary, truncated. With a handful
 * of runs over the same seed data, five rows read as near-identical sentences and the only
 * scannable difference was the score — a wall of text pretending to be a list.
 *
 * This shows what actually differs between runs: the score, the pass/fail split as a bar,
 * and how long ago. The prose still exists on the report itself, where there is room to
 * read it.
 */

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return days < 7 ? `${days}d ago` : formatIST(iso);
}

export function ReportRow({ report: r }: { report: ReportSummary }) {
  const total = r.passed + r.failed;
  const passPct = total ? (r.passed / total) * 100 : 100;
  const clean = r.failed === 0;

  return (
    <Link
      href={`/reports/${r.id}`}
      data-verdict={clean ? "pass" : "fail"}
      className="row-accent group flex items-center gap-4 px-4 py-3 transition-colors hover:bg-surface-2"
    >
      <span
        className={`w-16 shrink-0 text-right font-display text-xl font-bold tabular-nums leading-none ${
          clean ? "text-pass-fg" : "text-fail-fg"
        }`}
      >
        {r.score.toFixed(1)}
      </span>

      {/* Proportion, not just a score: the split is the thing you compare run to run. */}
      <span
        className="hidden h-6 w-32 shrink-0 overflow-hidden rounded sm:flex"
        style={{ background: "var(--fail-bg)" }}
        aria-hidden
      >
        <span
          className="h-full transition-[width] duration-500"
          style={{ width: `${passPct}%`, background: "var(--pass-bg)" }}
        />
      </span>

      <span className="flex min-w-0 flex-1 items-baseline gap-3">
        <span className="tabular-nums text-sm text-body">
          <span className="font-medium text-pass-fg">{r.passed}</span>
          <span className="text-faint"> pass</span>
          <span className="mx-1.5 text-faint">·</span>
          <span className={`font-medium ${clean ? "text-faint" : "text-fail-fg"}`}>
            {r.failed}
          </span>
          <span className="text-faint"> fail</span>
        </span>
        <span className="hidden truncate text-xs text-faint md:inline">
          {total} actions
        </span>
      </span>

      <span className="shrink-0 text-xs tabular-nums text-faint">
        {relativeTime(r.created_at)}
      </span>
      <span
        className="shrink-0 text-faint transition-transform duration-150 group-hover:translate-x-0.5"
        aria-hidden
      >
        ›
      </span>
    </Link>
  );
}
