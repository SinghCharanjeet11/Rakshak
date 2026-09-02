"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  getAudit,
  getRun,
  replayRun,
  type AuditView,
  type RunView,
} from "@/lib/api";
import { Field, Skeleton } from "./ui";

const SIGNAL_HELP: Record<string, string> = {
  membrane_rejection:
    "Fraction of submitted items that failed re-validation and never reached the engine.",
  injection_heuristic:
    "How strongly the submitted log reads as containing instructions aimed at the parser (OWASP LLM01).",
  tool_call_validity:
    "1.0 if the ingestion agent stayed inside its single permitted tool.",
  trajectory_cost: "Tokens spent on this turn.",
  parse_coverage: "Fraction of substantive log lines that became structured actions.",
};

const STATUS_STYLE: Record<string, string> = {
  done: "border-pass-border bg-pass-bg text-pass-fg",
  running: "border-line bg-surface-2 text-muted",
  halted_budget: "border-warn-border bg-warn-bg text-warn-fg",
  failed: "border-fail-border bg-fail-bg text-fail-fg",
};

/**
 * The run record, its budget spend, the non-blocking eval signals, and the append-only
 * audit trail.
 *
 * This panel is why the control plane is demonstrable rather than merely described: the
 * budget, the membrane rejection rate and the injection heuristic are all things the
 * architecture claims, and all things you can now point at on screen.
 */
export function RunEvidence({ runId }: { runId: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [run, setRun] = useState<RunView | null>(null);
  const [audit, setAudit] = useState<AuditView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [replaying, setReplaying] = useState(false);

  useEffect(() => {
    if (!open || run) return;
    Promise.all([getRun(runId), getAudit(runId)])
      .then(([r, a]) => {
        setRun(r);
        setAudit(a);
      })
      .catch((e: ApiError) => setError(e.detail));
  }, [open, run, runId]);

  const replay = async () => {
    setReplaying(true);
    try {
      const report = await replayRun(runId);
      router.push(`/reports/${report.id}`);
      router.refresh();
    } catch (e) {
      setError((e as ApiError).detail);
    } finally {
      setReplaying(false);
    }
  };

  return (
    <section className="card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-controls="run-evidence"
        className="flex w-full items-center gap-2 px-4 py-3 text-left hover:bg-surface-2"
      >
        <span className="text-sm font-semibold">Run &amp; evidence</span>
        <span className="clause">{runId}</span>
        <span className="ml-auto text-faint" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
      </button>

      {open && (
        <div id="run-evidence" className="border-t border-line px-4 py-4">
          {error && <p className="text-sm text-fail-fg">{error}</p>}
          {!run && !error && <Skeleton className="h-32 w-full" />}

          {run && audit && (
            <div className="space-y-5">
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div>
                  <div className="label">Status</div>
                  <span
                    className={`mt-1 inline-flex rounded border px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide ${
                      STATUS_STYLE[run.run.status] ?? STATUS_STYLE.running
                    }`}
                  >
                    {run.run.status.replace("_", " ")}
                  </span>
                </div>
                <Field
                  label="Duration"
                  value={run.duration_ms != null ? `${run.duration_ms} ms` : "—"}
                />
                <Field label="Rule-pack" value={run.run.rulepack_version} mono />
                <Field label="Tenant" value={run.run.tenant_id} mono />
              </div>

              <div>
                <div className="label mb-2">Budget</div>
                <div className="grid gap-2 sm:grid-cols-3">
                  <BudgetBar
                    label="Turns"
                    used={run.run.turns_used}
                    max={run.run.budget.max_total_turns}
                  />
                  <BudgetBar
                    label="Tokens"
                    used={run.run.tokens_used}
                    max={run.run.budget.max_tokens}
                  />
                  <BudgetBar
                    label="Cost (₹)"
                    used={run.run.cost_inr}
                    max={run.run.budget.max_cost_inr}
                    decimals={4}
                  />
                </div>
                <p className="mt-2 text-xs leading-relaxed text-faint">
                  Caps halt a run rather than warning about it: a run that would exceed one
                  ends <span className="font-mono">halted_budget</span> with a partial
                  report.
                </p>
              </div>

              <div>
                <div className="label mb-2">
                  Evaluation signals ({run.eval_signals.length})
                </div>
                {run.eval_signals.length === 0 ? (
                  <p className="text-xs text-faint">No signals recorded for this run.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {run.eval_signals.map((s, i) => (
                      <li
                        key={`${s.kind}-${i}`}
                        className="flex flex-wrap items-baseline gap-x-3 rounded bg-surface-2 px-3 py-2"
                      >
                        <span className="font-mono text-xs text-body">{s.kind}</span>
                        <span className="font-mono text-xs tabular-nums text-muted">
                          {s.value.toFixed(4)}
                        </span>
                        <span className="min-w-0 flex-1 text-xs text-faint">
                          {SIGNAL_HELP[s.kind] ?? ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <div className="label mb-2">
                  Audit trail ({audit.count} rows
                  {audit.append_only ? ", append-only" : ""})
                </div>
                <div className="max-h-56 overflow-y-auto rounded border border-line">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-surface-2">
                      <tr className="text-left">
                        <th scope="col" className="px-3 py-1.5 font-medium text-faint">Action</th>
                        <th scope="col" className="px-3 py-1.5 font-medium text-faint">Type</th>
                        <th scope="col" className="px-3 py-1.5 font-medium text-faint">Verdict</th>
                        <th scope="col" className="px-3 py-1.5 font-medium text-faint">Clause</th>
                      </tr>
                    </thead>
                    <tbody>
                      {audit.entries.map((e) => (
                        <tr key={e.id} className="border-t border-line">
                          <td className="px-3 py-1.5 font-mono text-muted">{e.action_id}</td>
                          <td className="px-3 py-1.5 text-muted">{e.action_type}</td>
                          <td
                            className={`px-3 py-1.5 font-medium ${
                              e.verdict === "fail" ? "text-fail-fg" : "text-pass-fg"
                            }`}
                          >
                            {e.verdict}
                          </td>
                          <td className="px-3 py-1.5 font-mono text-faint">
                            {e.clause ?? "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-faint">
                  The database refuses UPDATE and DELETE on this table outright, so the
                  trail is evidence rather than a log.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
                <button
                  type="button"
                  onClick={replay}
                  disabled={replaying}
                  className="btn"
                >
                  {replaying ? "Replaying…" : "Replay this run"}
                </button>
                <p className="text-xs leading-relaxed text-faint">
                  Re-verifies the stored raw log. Under the same rule-pack it returns the
                  identical report with no recompute — which is the determinism claim, shown
                  rather than asserted.
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function BudgetBar({
  label,
  used,
  max,
  decimals = 0,
}: {
  label: string;
  used: number;
  max: number;
  decimals?: number;
}) {
  const pct = max > 0 ? Math.min(100, (used / max) * 100) : 0;
  return (
    <div className="rounded border border-line px-3 py-2">
      <div className="flex items-baseline justify-between">
        <span className="text-xs text-muted">{label}</span>
        <span className="font-mono text-xs tabular-nums text-body">
          {used.toFixed(decimals)}
          <span className="text-faint"> / {max.toFixed(decimals)}</span>
        </span>
      </div>
      <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-track">
        <div
          className={`h-full rounded-full ${pct > 80 ? "bg-sev-high" : "bg-pass-fg"}`}
          style={{ width: `${Math.max(pct, used > 0 ? 2 : 0)}%` }}
        />
      </div>
    </div>
  );
}
