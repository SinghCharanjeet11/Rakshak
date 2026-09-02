"use client";

import { useMemo, useState } from "react";
import type { RulePackView, Severity } from "@/lib/api";
import { CopyButton, Segmented, SeverityTag, WarnNote } from "./ui";

type Scope = "all" | "debit" | "mandate_retry" | "contact" | "notify";

/**
 * Communicates "these are inspectable, versioned, and cite the law" (04-frontend.md §2).
 *
 * The unverified-value banner is deliberate. OPEN-2 records that an unconfirmed regulatory
 * number is the top project risk, and hiding that from the one screen a compliance officer
 * would actually audit would be the wrong kind of polish.
 */
export function RulePackViewer({ pack }: { pack: RulePackView }) {
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<Scope>("all");

  const rules = useMemo(() => {
    const needle = query.toLowerCase();
    return pack.rules
      .filter((r) => (scope === "all" ? true : r.applies_to.includes(scope)))
      .filter(
        (r) =>
          !needle ||
          [r.id, r.title, r.clause, r.condition_prose, r.source].some((f) =>
            f.toLowerCase().includes(needle),
          ),
      );
  }, [pack.rules, query, scope]);

  const bySeverity = useMemo(() => {
    const order: Severity[] = ["critical", "high", "medium", "low"];
    return order
      .map((s) => ({ s, n: pack.rules.filter((r) => r.severity === s).length }))
      .filter((x) => x.n > 0);
  }, [pack.rules]);

  return (
    <div className="space-y-6">
      <section className="card reveal p-5">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold">{pack.source}</h2>
            {pack.circular && (
              <p className="clause mt-1 inline-flex items-center gap-1">
                {pack.circular}
                <CopyButton value={pack.circular} label="copy" />
              </p>
            )}
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
          <span>{pack.rules.length} rules</span>
          <span>{pack.exemptions.length} exemptions</span>
          {bySeverity.map(({ s, n }) => (
            <span key={s}>
              {n} {s}
            </span>
          ))}
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {pack.sources.map((s) => (
            <div key={s.file} className="rounded-md border border-line bg-surface-2 px-3 py-2">
              <div className="font-mono text-xs text-body">{s.file}</div>
              <div className="mt-0.5 text-xs text-muted">
                {s.source} · v{s.version}
                {s.effective_from ? ` · effective ${s.effective_from}` : ""}
                {s.primary ? " · primary" : ""}
              </div>
            </div>
          ))}
        </div>

        {pack.unverified_rule_values.length > 0 && (
          <div className="mt-4">
            <WarnNote>
              <strong>
                {pack.unverified_rule_values.length} value(s) pending verification
              </strong>{" "}
              against the source circular:{" "}
              <span className="font-mono">
                {pack.unverified_rule_values.join(", ")}
              </span>
              . These are encoded from research, not confirmed from the published circular.
              Confirm each before relying on a verdict that turns on one of these numbers.
            </WarnNote>
          </div>
        )}
      </section>

      <section aria-labelledby="rules-heading">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <h3 id="rules-heading" className="text-sm font-semibold">
            Rules{" "}
            <span className="text-faint">
              ({rules.length}
              {rules.length !== pack.rules.length && ` of ${pack.rules.length}`})
            </span>
          </h3>

          <Segmented
            label="Filter by action type"
            value={scope}
            onChange={setScope}
            options={[
              { value: "all", label: "All" },
              { value: "debit", label: "Debit" },
              { value: "mandate_retry", label: "Retry" },
              { value: "contact", label: "Contact" },
              { value: "notify", label: "Notify" },
            ]}
          />

          <div className="w-full sm:ml-auto sm:w-auto">
            <label htmlFor="rule-search" className="sr-only">
              Search rules
            </label>
            <input
              id="rule-search"
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search rules and clauses…"
              className="input w-full sm:w-56"
            />
          </div>
        </div>

        {rules.length === 0 ? (
          <p className="card px-4 py-8 text-center text-sm text-muted">
            No rules match this filter.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {rules.map((r, i) => (
              <article
                key={r.id}
                className={`card card-interactive reveal p-4 d-${(i % 6) + 1}`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <SeverityTag severity={r.severity} />
                  <span className="font-mono text-xs text-muted">{r.id}</span>
                  {!r.value_verified && (
                    <span
                      title="Value not yet confirmed against the source circular"
                      className="rounded border border-warn-border bg-warn-bg px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-warn-fg"
                    >
                      unverified
                    </span>
                  )}
                </div>

                <h4 className="mt-2 text-sm font-medium text-body">{r.title}</h4>

                <p className="mt-2 rounded bg-surface-2 px-2 py-1.5 font-mono text-xs text-muted">
                  {r.condition_prose}
                </p>

                <dl className="mt-3 space-y-1.5 text-xs">
                  <div className="flex gap-2">
                    <dt className="label shrink-0">Applies to</dt>
                    <dd className="text-muted">{r.applies_to.join(", ")}</dd>
                  </div>
                  <div>
                    <dt className="label">Clause</dt>
                    <dd className="mt-0.5 flex flex-wrap items-center gap-1">
                      <span className="font-mono text-body">{r.clause}</span>
                      <CopyButton value={`${r.clause} — ${r.source}`} label="copy" />
                    </dd>
                    <dd className="clause mt-0.5">{r.source}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="exemptions-heading">
        <h3 id="exemptions-heading" className="mb-3 text-sm font-semibold">
          Exemptions <span className="text-faint">({pack.exemptions.length})</span>
        </h3>
        <div className="grid gap-3 sm:grid-cols-2">
          {pack.exemptions.map((e) => (
            <article
              key={e.id}
              className="card-interactive reveal rounded-lg border border-exempt-border bg-exempt-bg p-4"
            >
              <span className="font-mono text-xs text-muted">{e.id}</span>
              <h4 className="mt-2 text-sm font-medium text-body">{e.title}</h4>
              <p className="mt-2 text-xs leading-relaxed text-muted">
                Suppresses <span className="font-mono">{e.exempts.join(", ")}</span> when
                MCC is <span className="font-mono">{e.when_mcc_in.join(" or ")}</span>.
                It suppresses those rules only — nothing else is excused.
              </p>
              <div className="mt-3 text-xs">
                <div className="label">Clause</div>
                <div className="mt-0.5 font-mono text-body">{e.clause}</div>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
