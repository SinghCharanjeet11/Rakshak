/**
 * Typed fetch client — the single source of truth for the API contract on the frontend
 * (04-frontend.md §6). These types mirror `backend/app/core/models.py`; if one side
 * changes, both change.
 */

const BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

export type Severity = "critical" | "high" | "medium" | "low";

export type ActionType =
  | "mandate_retry"
  | "debit"
  | "notify"
  | "contact"
  | "escalate";

export interface Action {
  id: string;
  type: ActionType;
  mandate_id?: string | null;
  customer_id?: string | null;
  amount?: number | null;
  currency?: string;
  timestamp: string;
  retry_index?: number | null;
  window_start?: string | null;
  notice_sent_at?: string | null;
  debit_due_at?: string | null;
  afa_present?: boolean | null;
  mcc?: string | null;
  /** §8(b) categories. Closed on the backend, so an unknown value is a membrane
   *  rejection rather than something the UI ever has to render. */
  category?: "insurance_premium" | "mutual_fund_subscription" | "credit_card_bill" | null;
  channel?: string | null;
  dispute_active?: boolean | null;
  consent_opted_out?: boolean | null;
}

export interface Violation {
  action_id: string;
  rule_id: string;
  title: string;
  severity: Severity;
  offending_value: string;
  clause: string;
  source: string;
  explanation?: string | null;
}

/** Why an action passed despite a rule applying to it — e.g. the FASTag exemption. */
export interface ExemptionApplied {
  action_id: string;
  rule_id: string;
  exemption_id: string;
  reason: string;
  clause: string;
  source: string;
}

export interface Report {
  id: string;
  created_at: string;
  rulepack_version: string;
  actions: Action[];
  violations: Violation[];
  exemptions_applied: ExemptionApplied[];
  score: number;
  passed: number;
  failed: number;
  summary: string;
  correlation_id?: string | null;
  run_id?: string | null;
}

export interface EvalSignal {
  run_id: string;
  turn: number;
  kind: string;
  value: number;
  meta: Record<string, unknown>;
}

export interface RunView {
  run: {
    id: string;
    tenant_id: string;
    correlation_id: string;
    rulepack_version: string;
    status: "running" | "done" | "halted_budget" | "failed";
    budget: {
      max_turns: number;
      max_total_turns: number;
      max_tokens: number;
      max_cost_inr: number;
      max_actions: number;
    };
    tokens_used: number;
    cost_inr: number;
    turns_used: number;
    started_at: string;
    ended_at: string | null;
  };
  report_id: string | null;
  duration_ms: number | null;
  budget_remaining: { turns: number; tokens: number; cost_inr: number };
  eval_signals: EvalSignal[];
}

export interface AuditEntry {
  id: number;
  run_id: string;
  action_id: string;
  action_type: string;
  verdict: "pass" | "fail";
  rule_id: string | null;
  clause: string | null;
  created_at: string;
}

export interface AuditView {
  run_id: string;
  append_only: boolean;
  count: number;
  entries: AuditEntry[];
}

export interface ReportSummary {
  id: string;
  created_at: string;
  rulepack_version: string;
  score: number;
  passed: number;
  failed: number;
  summary: string;
}

export interface RuleView {
  id: string;
  title: string;
  applies_to: string[];
  severity: Severity;
  clause: string;
  source: string;
  condition: Record<string, unknown>;
  condition_prose: string;
  value_verified: boolean;
  verified_on: string | null;
  /**
   * The cited clause, verbatim. Display-only evidence: the reader compares it against
   * `condition_prose` and judges for themselves whether we read the law correctly,
   * rather than trusting a paragraph number they cannot check.
   */
  clause_text: string | null;
}

export interface ExemptionView {
  id: string;
  title: string;
  exempts: string[];
  /** Selectors are ANDed, and any of them may be empty — §6(d) matches on MCC alone,
   *  §8(b) on category plus an amount ceiling. Rendering must not assume MCC exists. */
  when_mcc_in: string[];
  when_category_in: string[];
  max_amount: number | null;
  clause: string;
  source: string;
  value_verified: boolean;
  verified_on: string | null;
  clause_text: string | null;
}

export interface RulePackView {
  version: string;
  source: string;
  circular: string | null;
  sources: {
    file: string;
    version: string;
    source: string;
    circular: string | null;
    effective_from: string | null;
    primary: boolean;
  }[];
  unverified_rule_values: string[];
  rules: RuleView[];
  exemptions: ExemptionView[];
}

/** Carries the backend's `detail` string so the UI can surface 422/400/502 inline. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      `Cannot reach the API at ${BASE}. Is the backend running on port 8000?`,
    );
  }

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail)) detail = JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as T;
}

export type SubmitFormat = "json" | "text" | "razorpay";

export function verifyBatch(body: {
  format: SubmitFormat;
  payload: unknown;
  rulepack_version?: string;
}): Promise<Report> {
  return request<Report>("/verify/batch", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export const getRun = (id: string) => request<RunView>(`/runs/${id}`);

export const getAudit = (id: string) => request<AuditView>(`/runs/${id}/audit`);

export const replayRun = (id: string, version?: string) =>
  request<Report>(
    `/runs/${id}/replay${version ? `?rulepack_version=${version}` : ""}`,
    { method: "POST" },
  );

export const getReport = (id: string) => request<Report>(`/reports/${id}`);

export const listReports = () =>
  request<{ total: number; reports: ReportSummary[] }>("/reports?limit=50");

export const getRules = (version?: string) =>
  request<RulePackView>(`/rules${version ? `?version=${version}` : ""}`);

export const getRuleVersions = () =>
  request<{ versions: string[] }>("/rules/versions");

export const getHealth = () =>
  request<{
    status: string;
    rulepack: string;
    rules_loaded: number;
    llm_enabled: boolean;
    unverified_rule_values: string[];
    /** A pack can go wrong without changing: the circular it cites may be amended or
     *  repealed. These report when that was last confirmed. */
    circular_checked_on: string | null;
    circular_check_age_days: number | null;
    circular_check_stale: boolean;
  }>("/health");

// ---------------------------------------------------------------------------
// display helpers
// ---------------------------------------------------------------------------

export const INR = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

/** Actions and verdicts are judged in IST; render them in IST so the two agree. */
export function formatIST(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** Minutes past midnight IST — the frame the quiet-hours rule is actually judged in. */
export function istMinutes(iso: string): number {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(new Date(iso));
  const h = Number(parts.find((p) => p.type === "hour")?.value ?? 0);
  const m = Number(parts.find((p) => p.type === "minute")?.value ?? 0);
  return (h % 24) * 60 + m;
}

export function istClock(iso: string): string {
  const m = istMinutes(iso);
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

export function violationsByAction(report: Report): Map<string, Violation[]> {
  const map = new Map<string, Violation[]>();
  for (const v of report.violations) {
    map.set(v.action_id, [...(map.get(v.action_id) ?? []), v]);
  }
  return map;
}

export function exemptionsByAction(report: Report): Map<string, ExemptionApplied[]> {
  const map = new Map<string, ExemptionApplied[]>();
  for (const e of report.exemptions_applied) {
    map.set(e.action_id, [...(map.get(e.action_id) ?? []), e]);
  }
  return map;
}
