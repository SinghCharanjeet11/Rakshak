"use client";

import { useState } from "react";
import { ApiError, draftRule, type RuleDraft } from "@/lib/api";
import { CopyButton, ErrorNote, WarnNote } from "@/components/ui";

/**
 * The maintenance answer, made demonstrable.
 *
 * The one real objection to a rule engine is "who maintains this when the regulator amends
 * the framework?" — and until this panel existed the answer was only written down. Here it
 * is operable: paste clause text, the model proposes an encoded entry, and a human commits
 * it by hand.
 *
 * Two things this deliberately shows rather than claims:
 *
 * 1. **The draft crosses the same membrane a verdict does.** The condition vocabulary is a
 *    closed set, so a model that invents `kind: vibes_based_check` is rejected by
 *    `Rule.model_validate` exactly as a hallucinated field on an `Action` is rejected at
 *    ingestion. `accepted` reports that structural check and nothing more — it never means
 *    "this rule is correct".
 * 2. **Nothing is written.** The endpoint has no access to the rules directory; the panel
 *    renders YAML for a human to review, edit and commit. The shipped artifact stays
 *    deterministic data rather than model output.
 */
export function RuleDrafter() {
  const [clause, setClause] = useState("");
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<RuleDraft | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const tooShort = clause.trim().length < 20;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (tooShort || busy) return;
    setBusy(true);
    setError(null);
    setDraft(null);
    try {
      setDraft(await draftRule({ clause_text: clause, hint: hint || undefined }));
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="drafter-heading" className="card p-4">
      <h2 id="drafter-heading" className="label">
        Draft a rule from regulation text
      </h2>
      <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-muted">
        When the regulator amends the framework, someone has to translate prose into an
        encoded rule. That is mechanical work, so a model does the first pass — then a human
        reviews and commits it. The draft crosses the <strong className="text-body">same
        closed-vocabulary membrane</strong> an ingested action does: a proposal naming a
        condition kind that does not exist is rejected here, not discovered in production.
      </p>

      <form onSubmit={submit} className="mt-4 space-y-3">
        <div>
          <label htmlFor="clause" className="label mb-1.5 block">
            Clause text
          </label>
          <textarea
            id="clause"
            value={clause}
            onChange={(e) => setClause(e.target.value)}
            rows={5}
            spellCheck={false}
            placeholder={
              "An issuer shall send a pre-transaction notification to the customer, at least 24 hours prior to the actual charge / debit."
            }
            className="w-full resize-y rounded-md border border-line bg-surface-2 p-3 font-mono text-xs leading-relaxed text-body outline-none placeholder:text-faint"
          />
        </div>

        <div>
          <label htmlFor="hint" className="label mb-1.5 block">
            Hint <span className="font-normal normal-case text-muted">(optional)</span>
          </label>
          <input
            id="hint"
            value={hint}
            onChange={(e) => setHint(e.target.value)}
            placeholder="e.g. this is an exemption, not a rule"
            className="w-full rounded-md border border-line bg-surface-2 px-3 py-2 text-sm text-body outline-none placeholder:text-faint"
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className="btn-primary" disabled={tooShort || busy}>
            {busy ? "Drafting…" : "Draft rule"}
          </button>
          <span className="text-xs text-muted">
            {tooShort
              ? "Paste at least 20 characters of clause text."
              : "Proposes only — this never writes to the rule-pack."}
          </span>
        </div>
      </form>

      {error && (
        <div className="mt-4">
          <ErrorNote title="Could not draft a rule">{error.detail}</ErrorNote>
        </div>
      )}

      {draft && (
        <div className="mt-5 space-y-3" aria-live="polite">
          {/*
            Three outcomes, not two, and conflating them would misdescribe the mechanism:

            - not drafted    — the model read the clause and reported it could not be
                               expressed in the closed vocabulary. Nothing was proposed.
            - drafted, refused — a proposal was made and the membrane threw it out.
            - drafted, accepted — it is structurally valid. Still not "correct".
          */}
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                draft.accepted
                  ? "bg-pass-bg text-pass-fg"
                  : draft.drafted
                    ? "bg-fail-bg text-fail-fg"
                    : "bg-warn-bg text-warn-fg"
              }`}
            >
              {draft.accepted
                ? "✓ crossed the membrane"
                : draft.drafted
                  ? "✕ rejected by the membrane"
                  : "— no rule proposed"}
            </span>
            {draft.kind && (
              <span className="rounded-full border border-line px-2.5 py-1 font-mono text-[11px] text-muted">
                {draft.kind}
              </span>
            )}
            <span className="text-[11px] tabular-nums text-muted">
              {draft.tokens_used.toLocaleString()} tokens · ₹{draft.cost_inr.toFixed(4)}
            </span>
          </div>

          {/* The refusal is the interesting case, not the failure case: it is the membrane
              doing its job on the authoring path rather than the verdict path. */}
          {draft.drafted && !draft.accepted && draft.rejection && (
            <WarnNote>
              <strong className="font-medium">The proposal was refused:</strong>{" "}
              {draft.rejection}
              <span className="mt-1 block text-xs">
                This is the closed condition vocabulary working. A rule the engine could not
                evaluate never reaches a reviewer, let alone the pack.
              </span>
            </WarnNote>
          )}

          {!draft.drafted && (
            <WarnNote>
              <strong className="font-medium">
                The model did not propose a rule.
              </strong>{" "}
              It reported that the clause cannot be expressed in the six condition kinds the
              engine understands.
              <span className="mt-1 block text-xs">
                This is the honest outcome, not a failure. Encoding it anyway would mean
                inventing a condition the engine cannot evaluate — the clause needs a human
                to decide whether it warrants a new kind.
              </span>
            </WarnNote>
          )}

          {draft.reason && (
            <div>
              <div className="label mb-1">Model&apos;s reasoning</div>
              <p className="text-sm leading-relaxed text-body">{draft.reason}</p>
            </div>
          )}

          {draft.yaml && (
            <div>
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="label">Proposed entry</span>
                <CopyButton value={draft.yaml} label="copy YAML" />
              </div>
              <pre className="max-h-80 overflow-auto rounded-md border border-line bg-surface-2 p-3 font-mono text-[12px] leading-relaxed text-body">
                {draft.yaml}
              </pre>
            </div>
          )}

          {draft.review_required && (
            <p className="rounded-md border border-line bg-surface-2 px-3 py-2 text-xs leading-relaxed text-muted">
              <strong className="text-body">Nothing was written.</strong> This endpoint has
              no access to the rules directory — the active pack is byte-identical before and
              after this call, and a test pins that. Review the YAML, set{" "}
              <code className="font-mono">value_verified</code> yourself once you have read
              the clause in the primary source, and commit it by hand.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
