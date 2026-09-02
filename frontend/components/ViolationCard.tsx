"use client";

import type { ExemptionApplied, Violation } from "@/lib/api";
import { CopyButton, SeverityTag } from "./ui";

/**
 * The credibility moment (04-frontend.md §2). The clause and source circular get their own
 * row in monospace and a copy button, because "cites the law" is the whole product and the
 * single most likely next action is pasting that citation into a ticket.
 */
export function ViolationCard({ violation }: { violation: Violation }) {
  return (
    <article className="reveal rounded-md border border-fail-border bg-fail-bg p-4">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityTag severity={violation.severity} />
        <span className="font-mono text-xs text-muted">{violation.rule_id}</span>
      </div>

      <h4 className="mt-2 text-sm font-semibold text-body">{violation.title}</h4>

      <dl className="mt-3 space-y-2">
        <div>
          <dt className="label">Offending value</dt>
          <dd className="mt-0.5 font-mono text-xs text-fail-fg">
            {violation.offending_value}
          </dd>
        </div>
        <div>
          <dt className="label">Clause</dt>
          <dd className="mt-0.5 flex flex-wrap items-center gap-1">
            <span className="font-mono text-xs text-body">{violation.clause}</span>
            <CopyButton
              value={`${violation.clause} — ${violation.source}`}
              label="copy"
            />
          </dd>
          <dd className="clause mt-0.5">{violation.source}</dd>
        </div>
      </dl>

      {violation.explanation ? (
        <p className="mt-3 border-t border-fail-border pt-3 text-sm leading-relaxed text-muted">
          {violation.explanation}
        </p>
      ) : (
        <p className="mt-3 border-t border-fail-border pt-3 text-xs italic text-faint">
          Explanation unavailable — the verdict above stands on its own. It was decided by
          the rule engine and does not depend on the model layer.
        </p>
      )}
    </article>
  );
}

/** Shown where a rule applied but an exemption suppressed it — the FASTag case. */
export function ExemptionCard({ exemption }: { exemption: ExemptionApplied }) {
  return (
    <article className="reveal rounded-md border border-exempt-border bg-exempt-bg p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center rounded border border-exempt-border bg-surface px-1.5 py-0.5 text-[11px] font-medium uppercase tracking-wide text-exempt-fg">
          exempt
        </span>
        <span className="font-mono text-xs text-muted">
          {exemption.exemption_id}
        </span>
      </div>

      <h4 className="mt-2 text-sm font-semibold text-body">{exemption.reason}</h4>
      <p className="mt-1 text-sm leading-relaxed text-muted">
        <span className="font-mono text-xs">{exemption.rule_id}</span> applies to this
        action, but an exemption suppresses it — so this passes on the merits, not by
        oversight.
      </p>

      <div className="mt-3">
        <div className="label">Clause</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-1">
          <span className="font-mono text-xs text-body">{exemption.clause}</span>
          <CopyButton value={`${exemption.clause} — ${exemption.source}`} label="copy" />
        </div>
        <div className="clause mt-0.5">{exemption.source}</div>
      </div>
    </article>
  );
}
