"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Fragment, useMemo, useState } from "react";
import {
  exemptionsByAction,
  formatIST,
  INR,
  violationsByAction,
  type Action,
  type Report,
} from "@/lib/api";
import { ExemptionCard, ViolationCard } from "./ViolationCard";
import { Field, Segmented, VerdictPill, type Verdict } from "./ui";

type Filter = "all" | "fail" | "exempt" | "pass";

function keyFields(a: Action): string {
  const bits: string[] = [];
  if (a.amount != null) bits.push(INR.format(a.amount));
  if (a.retry_index != null) bits.push(`attempt ${a.retry_index}`);
  if (a.mcc) bits.push(`mcc ${a.mcc}`);
  if (a.channel) bits.push(a.channel);
  return bits.join(" · ") || "—";
}

function matches(a: Action, q: string): boolean {
  if (!q) return true;
  const needle = q.toLowerCase();
  return [a.id, a.type, a.mandate_id, a.customer_id, a.mcc]
    .filter(Boolean)
    .some((f) => String(f).toLowerCase().includes(needle));
}

export function ActionTable({ report }: { report: Report }) {
  const reduced = useReducedMotion();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");

  const violations = useMemo(() => violationsByAction(report), [report]);
  const exemptions = useMemo(() => exemptionsByAction(report), [report]);

  const verdictOf = useMemo(
    () =>
      (a: Action): Verdict => {
        if (violations.has(a.id)) return "fail";
        if (exemptions.has(a.id)) return "exempt";
        return "pass";
      },
    [violations, exemptions],
  );

  const counts = useMemo(() => {
    const c = { all: report.actions.length, fail: 0, exempt: 0, pass: 0 };
    for (const a of report.actions) c[verdictOf(a)] += 1;
    return c;
  }, [report.actions, verdictOf]);

  const rows = useMemo(() => {
    const rank: Record<Verdict, number> = { fail: 0, exempt: 1, pass: 2 };
    return report.actions
      .filter((a) => (filter === "all" ? true : verdictOf(a) === filter))
      .filter((a) => matches(a, query))
      .slice()
      .sort((x, y) => rank[verdictOf(x)] - rank[verdictOf(y)]);
  }, [report.actions, filter, query, verdictOf]);

  const drillableIds = useMemo(
    () => report.actions.filter((a) => verdictOf(a) !== "pass").map((a) => a.id),
    [report.actions, verdictOf],
  );
  const allOpen =
    drillableIds.length > 0 && drillableIds.every((id) => expanded.has(id));

  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  if (report.actions.length === 0) {
    return (
      <section className="card p-6">
        <h2 className="text-sm font-semibold">No actions in this report</h2>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
          Every submitted item was rejected by the validation membrane before it could
          reach the rule engine — most often a wrong <code className="font-mono">type</code>,
          a malformed timestamp, or a field that is not in the schema. Nothing was judged,
          so nothing passed.
        </p>
      </section>
    );
  }

  return (
    <section className="card reveal d-1 overflow-hidden" aria-label="Actions">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold">Actions</h2>

        <Segmented
          label="Filter by verdict"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: "All", count: counts.all },
            { value: "fail", label: "Fail", count: counts.fail },
            { value: "exempt", label: "Exempt", count: counts.exempt },
            { value: "pass", label: "Pass", count: counts.pass },
          ]}
        />

        <div className="flex w-full items-center gap-2 sm:ml-auto sm:w-auto">
          <label htmlFor="action-search" className="sr-only">
            Search actions
          </label>
          <input
            id="action-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search id, mandate, customer…"
            className="input w-full no-print sm:w-52"
          />
          {drillableIds.length > 0 && (
            <button
              type="button"
              onClick={() =>
                setExpanded(allOpen ? new Set() : new Set(drillableIds))
              }
              className="btn no-print"
            >
              {allOpen ? "Collapse all" : "Expand all"}
            </button>
          )}
        </div>
      </div>

      {rows.length === 0 ? (
        <p className="px-4 py-8 text-center text-sm text-muted">
          No actions match this filter.
        </p>
      ) : (
        <div className="scroll-x">
          <table className="w-full text-sm">
            <caption className="sr-only">
              {rows.length} of {report.actions.length} actions, failures first.
            </caption>
            {/* Not sticky, deliberately. `overflow-x-auto` on the wrapper makes that div
                the nearest scrolling ancestor, so a sticky thead pins to a box that never
                scrolls vertically and silently does nothing. Fixing it properly would mean
                giving the tbody its own fixed-height scroll region, which is worse on a
                page meant to be printed. The batch is tens of rows, not thousands. */}
            <thead className="bg-surface-2">
              <tr className="border-b border-line text-left">
                <th scope="col" className="label px-4 py-2 font-medium">Action</th>
                <th scope="col" className="label px-4 py-2 font-medium">Type</th>
                <th scope="col" className="label hidden px-4 py-2 font-medium sm:table-cell">
                  Detail
                </th>
                <th scope="col" className="label hidden px-4 py-2 font-medium md:table-cell">
                  Time (IST)
                </th>
                <th scope="col" className="label px-4 py-2 font-medium">Verdict</th>
                <th scope="col" className="w-10 px-2 py-2">
                  <span className="sr-only">Details</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => {
                const verdict = verdictOf(a);
                const rowViolations = violations.get(a.id) ?? [];
                const rowExemptions = exemptions.get(a.id) ?? [];
                const drillable = verdict !== "pass";
                const isOpen = expanded.has(a.id);
                const panelId = `detail-${a.id}`;

                return (
                  <Fragment key={a.id}>
                    <tr
                      onClick={() => drillable && toggle(a.id)}
                      data-verdict={verdict}
                      className={[
                        "row-accent border-b border-line align-middle transition-colors duration-150",
                        drillable ? "cursor-pointer" : "",
                        verdict === "fail"
                          ? "bg-fail-bg/50 hover:bg-fail-bg"
                          : "hover:bg-surface-2",
                      ].join(" ")}
                    >
                      <th
                        scope="row"
                        className="px-4 py-3 text-left font-mono text-xs font-normal text-muted"
                      >
                        {a.id}
                      </th>
                      <td className="px-4 py-3 text-body">{a.type}</td>
                      <td className="hidden px-4 py-3 tabular-nums text-muted sm:table-cell">
                        {keyFields(a)}
                      </td>
                      <td className="hidden px-4 py-3 tabular-nums text-muted md:table-cell">
                        {formatIST(a.timestamp)}
                      </td>
                      <td className="px-4 py-3">
                        <VerdictPill verdict={verdict} />
                      </td>
                      <td className="px-2 py-3">
                        {drillable && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggle(a.id);
                            }}
                            aria-expanded={isOpen}
                            aria-controls={panelId}
                            className="rounded px-1.5 py-0.5 text-faint transition-all duration-150 hover:scale-110 hover:bg-surface-3 hover:text-body"
                          >
                            <span aria-hidden>{isOpen ? "▾" : "▸"}</span>
                            <span className="sr-only">
                              {isOpen ? "Hide" : "Show"} details for {a.id}
                            </span>
                          </button>
                        )}
                      </td>
                    </tr>

                    <AnimatePresence initial={false}>
                      {isOpen && drillable && (
                        <tr id={panelId}>
                          <td colSpan={6} className="p-0">
                            <motion.div
                              initial={{ height: 0, opacity: 0 }}
                              animate={{ height: "auto", opacity: 1 }}
                              exit={{ height: 0, opacity: 0 }}
                              transition={{
                                duration: reduced ? 0 : 0.18,
                                ease: "easeOut",
                              }}
                              className="overflow-hidden"
                            >
                              <div className="space-y-3 border-b border-line bg-surface px-4 py-4">
                                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
                                  <Field label="Time (IST)" value={formatIST(a.timestamp)} />
                                  {a.mandate_id && (
                                    <Field label="Mandate" value={a.mandate_id} mono />
                                  )}
                                  {a.customer_id && (
                                    <Field label="Customer" value={a.customer_id} mono />
                                  )}
                                  {a.amount != null && (
                                    <Field label="Amount" value={INR.format(a.amount)} />
                                  )}
                                  {a.notice_sent_at && (
                                    <Field
                                      label="Notice sent"
                                      value={formatIST(a.notice_sent_at)}
                                    />
                                  )}
                                  {a.debit_due_at && (
                                    <Field
                                      label="Debit due"
                                      value={formatIST(a.debit_due_at)}
                                    />
                                  )}
                                  {a.retry_index != null && (
                                    <Field label="Attempt" value={String(a.retry_index)} />
                                  )}
                                  {a.mcc && <Field label="MCC" value={a.mcc} mono />}
                                  {a.afa_present != null && (
                                    <Field
                                      label="AFA"
                                      value={a.afa_present ? "collected" : "not collected"}
                                    />
                                  )}
                                  {a.dispute_active != null && (
                                    <Field
                                      label="Dispute"
                                      value={a.dispute_active ? "active" : "none"}
                                    />
                                  )}
                                  {a.consent_opted_out != null && (
                                    <Field
                                      label="Consent"
                                      value={a.consent_opted_out ? "opted out" : "opted in"}
                                    />
                                  )}
                                </div>

                                {rowViolations.map((v) => (
                                  <ViolationCard key={v.rule_id} violation={v} />
                                ))}
                                {rowExemptions.map((e) => (
                                  <ExemptionCard key={e.exemption_id} exemption={e} />
                                ))}
                              </div>
                            </motion.div>
                          </td>
                        </tr>
                      )}
                    </AnimatePresence>
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
