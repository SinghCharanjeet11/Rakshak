"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ScoreTrend } from "@/components/charts/ScoreTrend";
import { SeverityBar } from "@/components/charts/SeverityBar";
import { ViolationsByRule } from "@/components/charts/ViolationsByRule";
import { ReportRow } from "@/components/ReportRow";
import { ErrorNote, Skeleton, WarnNote } from "@/components/ui";
import {
  ApiError,
  getHealth,
  getReport,
  listReports,
  type Report,
  type ReportSummary,
} from "@/lib/api";

interface Health {
  rulepack: string;
  rules_loaded: number;
  llm_enabled: boolean;
  unverified_rule_values: string[];
}

export default function HomePage() {
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const [latest, setLatest] = useState<Report | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    listReports()
      .then((r) => {
        setReports(r.reports);
        // One extra fetch so the dashboard can show the shape of the most recent batch,
        // not just its score — the list endpoint deliberately omits violations.
        if (r.reports[0]) getReport(r.reports[0].id).then(setLatest).catch(() => undefined);
      })
      .catch(setError);
    getHealth().then(setHealth).catch(() => undefined);
  }, []);

  const totalActions = reports?.reduce((n, r) => n + r.passed + r.failed, 0) ?? 0;
  const totalFailed = reports?.reduce((n, r) => n + r.failed, 0) ?? 0;
  const failRate = totalActions ? (totalFailed / totalActions) * 100 : 0;

  return (
    <div className="space-y-5">
      <section className="reveal flex flex-wrap items-start justify-between gap-4">
        <div>
          <span className="eyebrow">Compliance overview</span>
          <h1 className="page-title">Dashboard</h1>
          <p className="page-lede">
            Rakshak checks what an autonomous payment-recovery agent proposes to do against
            the RBI E-mandate Framework 2026 and NPCI mandate rules, and reports every
            breach with the clause it violates.
          </p>
        </div>
        <Link href="/verify" className="btn-primary shrink-0">
          Run a verification
        </Link>
      </section>

      {error && error.status === 0 ? (
        <ErrorNote title="Backend unreachable">
          {error.detail}
          <p className="mt-2 font-mono text-xs">
            cd backend &amp;&amp; .venv\Scripts\python.exe -m uvicorn app.main:app --reload
            --port 8000
          </p>
        </ErrorNote>
      ) : (
        error && <ErrorNote title="Could not load reports">{error.detail}</ErrorNote>
      )}

      <section className="reveal d-1 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {health ? (
          <>
            <Stat
              label="Violation rate"
              value={reports && totalActions ? `${failRate.toFixed(1)}%` : "—"}
              hint={reports ? `${totalFailed} of ${totalActions} actions` : undefined}
              tone={failRate > 0 ? "fail" : "pass"}
              emphasis
            />
            <Stat
              label="Actions checked"
              value={reports ? String(totalActions) : "—"}
              hint={reports ? `across ${reports.length} runs` : undefined}
            />
            <Stat label="Rules active" value={String(health.rules_loaded)}
                  hint="deterministic, versioned YAML" />
            <Stat
              label="Model layer"
              value={health.llm_enabled ? "enabled" : "not needed"}
              hint={health.llm_enabled ? "free-text parsing on" : "JSON verifies without it"}
            />
          </>
        ) : (
          !error && [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[92px] w-full" />)
        )}
      </section>

      {health && health.unverified_rule_values.length > 0 && (
        <WarnNote>
          <strong>
            {health.unverified_rule_values.length} regulatory value(s) pending verification
          </strong>{" "}
          against the source circular. A wrong threshold is the one failure that discredits
          a compliance tool, so it is surfaced here rather than hidden — see the{" "}
          <Link href="/rules" className="underline underline-offset-2">
            rule-pack
          </Link>
          .
        </WarnNote>
      )}

      {reports && reports.length > 0 && (
        <section className="reveal d-3 grid items-start gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <ScoreTrend reports={reports} />
          </div>
          {latest ? <SeverityBar report={latest} /> : <Skeleton className="h-44 w-full" />}
        </section>
      )}

      {latest && latest.violations.length > 0 && (
        <section className="grid items-start gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <ViolationsByRule report={latest} />
          </div>
          <div className="card flex flex-col justify-between p-4">
            <div>
              <h3 className="section-title">Latest batch</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted">{latest.summary}</p>
            </div>
            <Link href={`/reports/${latest.id}`} className="btn mt-4 self-start">
              Open report
            </Link>
          </div>
        </section>
      )}

      <section aria-labelledby="recent-heading" className="reveal d-5">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 id="recent-heading" className="section-title">Recent reports</h2>
          {reports && reports.length > 0 && (
            <span className="text-xs text-faint">{reports.length} runs</span>
          )}
        </div>

        {!reports && !error && <Skeleton className="h-32 w-full" />}

        {reports?.length === 0 && (
          <div className="card px-6 py-12 text-center">
            <p className="text-sm text-muted">No verifications yet.</p>
            <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-faint">
              The verify screen ships with sample batches — including one with six planted
              violations and a FASTag debit that must pass.
            </p>
            <Link href="/verify" className="btn-primary mt-4">
              Run your first verification
            </Link>
          </div>
        )}

        {reports && reports.length > 0 && (
          <ul className="card divide-y divide-line overflow-hidden">
            {reports.map((r) => (
              <li key={r.id}>
                <ReportRow report={r} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
  tone,
  emphasis,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "pass" | "fail";
  emphasis?: boolean;
}) {
  const toneClass =
    tone === "fail" ? "text-fail-fg" : tone === "pass" ? "text-pass-fg" : "text-body";
  return (
    <div
      className="card lift px-4 py-3.5"
      style={
        emphasis
          ? { borderColor: "var(--brand-ring)", background: "var(--brand-soft)" }
          : undefined
      }
    >
      <div className="label">{label}</div>
      <div className={`stat-value mt-1.5 ${toneClass}`}>{value}</div>
      {hint && <div className="mt-1.5 text-xs text-faint">{hint}</div>}
    </div>
  );
}
