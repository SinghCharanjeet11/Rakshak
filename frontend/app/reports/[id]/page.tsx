"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ActionTable } from "@/components/ActionTable";
import { ComplianceScore } from "@/components/ComplianceScore";
import { RunEvidence } from "@/components/RunEvidence";
import { DayTimeline } from "@/components/charts/DayTimeline";
import { SeverityBar } from "@/components/charts/SeverityBar";
import { ViolationsByRule } from "@/components/charts/ViolationsByRule";
import { ErrorNote, Skeleton } from "@/components/ui";
import { ApiError, formatIST, getReport, type Report } from "@/lib/api";

export default function ReportPage({ params }: { params: { id: string } }) {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    setReport(null);
    setError(null);
    getReport(params.id).then(setReport).catch(setError);
  }, [params.id]);

  if (error) {
    return (
      <div className="space-y-4">
        <ErrorNote
          title={error.status === 404 ? "No such report" : "Could not load the report"}
        >
          {error.detail}
        </ErrorNote>
        <Link href="/verify" className="btn">
          Run a new verification
        </Link>
      </div>
    );
  }

  // Skeletons mirror the final layout so the page does not jump when it resolves.
  if (!report) {
    return (
      <div className="space-y-5">
        <Skeleton className="h-7 w-52" />
        <Skeleton className="h-40 w-full" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-44 w-full" />
          <Skeleton className="h-44 w-full" />
        </div>
        <Skeleton className="h-56 w-full" />
        <span className="sr-only" aria-live="polite">
          Loading report…
        </span>
      </div>
    );
  }

  const download = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${report.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-5">
      <div className="reveal flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Compliance report</h1>
          <p className="mt-0.5 text-xs text-faint">
            {formatIST(report.created_at)} IST
          </p>
        </div>
        <div className="no-print flex items-center gap-2">
          <button type="button" onClick={download} className="btn">
            Download JSON
          </button>
          <button type="button" onClick={() => window.print()} className="btn">
            Print
          </button>
          <Link href="/verify" className="btn-primary">
            New verification
          </Link>
        </div>
      </div>

      <ComplianceScore report={report} />

      {/* items-start so each card keeps its natural height — stretching the shorter one
          to match its neighbour just manufactures dead space. */}
      <div className="reveal d-2 grid items-start gap-4 lg:grid-cols-2">
        <SeverityBar report={report} />
        <ViolationsByRule report={report} />
      </div>

      <div className="reveal d-3">
        <DayTimeline report={report} />
      </div>

      <ActionTable report={report} />

      {report.run_id && (
        <div className="reveal d-5 no-print">
          <RunEvidence runId={report.run_id} />
        </div>
      )}

      <p className="reveal d-6 max-w-3xl text-xs leading-relaxed text-faint">
        Every verdict above was produced by the deterministic rule engine from the submitted
        facts and the rule-pack cited above. Explanations, where present, are
        written by the model layer after the verdict was decided and cannot change one.
      </p>
    </div>
  );
}
