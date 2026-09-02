"use client";

import {
  exemptionsByAction,
  istClock,
  istMinutes,
  violationsByAction,
  type Report,
} from "@/lib/api";
import { ChartCard, EmptyChart, Legend, Tooltip, useTooltip } from "./primitives";

type Verdict = "pass" | "fail" | "exempt";

const VERDICT_VAR: Record<Verdict, string> = {
  fail: "var(--fail-fg)",
  exempt: "var(--exempt-fg)",
  pass: "var(--pass-fg)",
};

const LANES = ["debit", "mandate_retry", "contact", "notify", "escalate"] as const;

// The quiet-hours window from the rule-pack: contact is permitted 08:00–19:00 IST.
// Corrected 2026-09-02 alongside the rule itself (RBI Fair Practices Code). These MUST
// track `QUIET_HOURS` in npci_mandate.yaml — a band that disagrees with the verdict is
// worse than no band, because the picture is what people believe.
const QUIET_START = 8 * 60;
const QUIET_END = 19 * 60;

/**
 * Every action laid out across one 24-hour day in IST, in a lane per action type.
 *
 * This is the chart worth having, because it renders the *rule* rather than just the
 * result: the permitted contact window is drawn as a band, so the 23:30 outreach is
 * visibly outside it. You do not have to trust the verdict — you can see why it was made.
 *
 * IST because that is the timezone the engine judges quiet hours in; showing local time
 * here would let the picture and the verdict disagree.
 */
export function DayTimeline({ report }: { report: Report }) {
  const { tip, show, hide } = useTooltip();

  const violations = violationsByAction(report);
  const exemptions = exemptionsByAction(report);
  const verdictOf = (id: string): Verdict =>
    violations.has(id) ? "fail" : exemptions.has(id) ? "exempt" : "pass";

  const lanes = LANES.map((type) => ({
    type,
    items: report.actions
      .filter((a) => a.type === type)
      .map((a) => ({
        id: a.id,
        m: istMinutes(a.timestamp),
        clock: istClock(a.timestamp),
        verdict: verdictOf(a.id),
        rules: (violations.get(a.id) ?? []).map((v) => v.rule_id),
      })),
  })).filter((l) => l.items.length > 0);

  if (report.actions.length === 0) {
    return (
      <ChartCard title="Action timeline">
        <EmptyChart>No actions to place on a timeline.</EmptyChart>
      </ChartCard>
    );
  }

  const LANE_H = 30;
  const height = lanes.length * LANE_H;
  const pctOf = (m: number) => (m / 1440) * 100;

  return (
    <ChartCard
      title="Action timeline"
      hint="24h, IST — the frame the rules are judged in"
      legend={
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
          <Legend
            items={[
              { label: "pass", color: VERDICT_VAR.pass },
              { label: "fail", color: VERDICT_VAR.fail },
              { label: "exempt", color: VERDICT_VAR.exempt },
            ]}
          />
          <span className="inline-flex items-center gap-1.5 text-xs text-muted">
            <span
              className="h-2 w-4 rounded-[2px] border border-line"
              style={{ background: "var(--surface-2)" }}
              aria-hidden
            />
            contact permitted 08:00–19:00
          </span>
        </div>
      }
      table={
        <table className="w-full text-xs">
          <tbody>
            {lanes.flatMap((l) =>
              l.items.map((it) => (
                <tr key={it.id} className="border-b border-line last:border-0">
                  <td className="py-1 font-mono text-muted">{it.id}</td>
                  <td className="py-1 text-muted">{l.type}</td>
                  <td className="py-1 tabular-nums text-body">{it.clock}</td>
                  <td className="py-1 text-right text-body">{it.verdict}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      }
    >
      <div className="scroll-x">
        <div className="relative min-w-[30rem]">
        {/* hour grid + permitted-window band */}
        <div className="relative" style={{ height }}>
          <svg
            viewBox={`0 0 100 ${height}`}
            preserveAspectRatio="none"
            className="absolute inset-0 h-full w-full"
            aria-hidden
          >
            <rect
              x={pctOf(QUIET_START)}
              y={0}
              width={pctOf(QUIET_END) - pctOf(QUIET_START)}
              height={height}
              fill="var(--surface-2)"
            />
            {[0, 3, 6, 9, 12, 15, 18, 21, 24].map((h) => (
              <line
                key={h}
                x1={pctOf(h * 60)}
                x2={pctOf(h * 60)}
                y1={0}
                y2={height}
                stroke="var(--grid)"
                strokeWidth={0.15}
                vectorEffect="non-scaling-stroke"
              />
            ))}
          </svg>

          {lanes.map((lane, li) => (
            <div
              key={lane.type}
              className="absolute left-0 right-0"
              style={{ top: li * LANE_H, height: LANE_H }}
            >
              <span className="absolute left-1 top-0.5 z-10 font-mono text-[10px] text-faint">
                {lane.type}
              </span>
              {lane.items.map((it, di) => (
                <button
                  key={it.id}
                  type="button"
                  onMouseMove={(e) =>
                    show(
                      e as unknown as React.MouseEvent,
                      it.id,
                      [
                        { label: lane.type, value: `${it.clock} IST` },
                        {
                          label: "verdict",
                          value: it.verdict,
                          color: VERDICT_VAR[it.verdict],
                        },
                        ...it.rules.map((r) => ({ label: "rule", value: r })),
                      ],
                    )
                  }
                  onMouseLeave={hide}
                  onFocus={() => undefined}
                  className="absolute top-[15px] h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 transition-transform duration-150 hover:scale-150"
                  style={{
                    left: `${pctOf(it.m)}%`,
                    background: VERDICT_VAR[it.verdict],
                    animation: `pop-in 340ms cubic-bezier(0.22,1,0.36,1) ${(li * 60) + di * 35}ms both`,
                    // a surface ring keeps overlapping marks separable
                    ["--tw-ring-color" as string]: "var(--surface)",
                  }}
                  aria-label={`${it.id}, ${lane.type} at ${it.clock} IST, ${it.verdict}`}
                />
              ))}
            </div>
          ))}
        </div>

        <div className="mt-1 flex justify-between font-mono text-[10px] text-faint">
          {[0, 6, 12, 18, 24].map((h) => (
            <span key={h}>{String(h).padStart(2, "0")}:00</span>
          ))}
        </div>

        <Tooltip tip={tip} />
        </div>
      </div>
    </ChartCard>
  );
}
