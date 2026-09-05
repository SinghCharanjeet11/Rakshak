"use client";

import { useEffect, useState } from "react";
import { RuleDrafter } from "@/components/RuleDrafter";
import { RulePackViewer } from "@/components/RulePackViewer";
import { ErrorNote, Skeleton } from "@/components/ui";
import { ApiError, getRules, type RulePackView } from "@/lib/api";

export default function RulesPage() {
  const [pack, setPack] = useState<RulePackView | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    getRules().then(setPack).catch(setError);
  }, []);

  return (
    <div className="space-y-6">
      <div className="reveal">
        <h1 className="text-lg font-semibold tracking-tight">Rule-pack</h1>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
          The rules are a versioned YAML artifact, not code. When the regulation changes you
          bump the pack — the engine does not change. Every rule cites the clause it comes
          from, and the condition vocabulary is a closed set of six kinds, so a pack naming
          an unknown one fails to load rather than being silently skipped.
        </p>
      </div>

      {error && (
        <ErrorNote title="Could not load the rule-pack">{error.detail}</ErrorNote>
      )}
      {!pack && !error && (
        <>
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-96 w-full" />
        </>
      )}
      {pack && <RulePackViewer pack={pack} />}

      {/* Below the pack, deliberately: the shipped artifact is the thing that matters, and
          the drafter is how the next entry gets proposed — not a way to change this one. */}
      <RuleDrafter />
    </div>
  );
}
