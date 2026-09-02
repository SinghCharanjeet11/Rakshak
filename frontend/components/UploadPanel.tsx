"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  getRuleVersions,
  verifyBatch,
  type SubmitFormat,
} from "@/lib/api";
import { SAMPLES } from "@/lib/samples";
import { Select } from "./Select";
import { ErrorNote, Segmented } from "./ui";

const FORMAT_LABEL: Record<SubmitFormat, string> = {
  json: "Structured JSON",
  text: "Free text",
  razorpay: "Razorpay webhooks",
};

const FORMAT_HELP: Record<SubmitFormat, string> = {
  json: "Skips the model layer entirely. Verifies in well under a second.",
  text: "Parsed by the ingestion agent, then re-validated before any rule runs. Needs OPENAI_API_KEY; expect a few seconds.",
  razorpay:
    "Mapped to actions by a deterministic adapter — no model. Compliance evidence is read from each entity's rakshak_* notes.",
};

/** Cheap client-side shape check, so an obvious mistake is caught before a round-trip. */
function inspect(raw: string, format: SubmitFormat) {
  if (!raw.trim()) return { ok: false as const, note: "" };
  if (format === "text") {
    const lines = raw.split("\n").filter((l) => l.trim()).length;
    return { ok: true as const, note: `${lines} non-empty lines` };
  }
  try {
    const parsed = JSON.parse(raw);
    if (format === "razorpay") {
      const events = Array.isArray(parsed)
        ? parsed
        : Array.isArray(parsed?.events)
          ? parsed.events
          : [parsed];
      return { ok: true as const, note: `${events.length} webhook events` };
    }
    if (!Array.isArray(parsed)) {
      return {
        ok: false as const,
        note: "Expected a JSON array of actions.",
      };
    }
    return { ok: true as const, note: `${parsed.length} actions` };
  } catch (e) {
    return { ok: false as const, note: (e as Error).message };
  }
}

export function UploadPanel() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);

  const [format, setFormat] = useState<SubmitFormat>("json");
  const [raw, setRaw] = useState("");
  const [versions, setVersions] = useState<string[]>([]);
  const [version, setVersion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ title: string; body: string } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [loadedSample, setLoadedSample] = useState<string | null>(null);

  useEffect(() => {
    getRuleVersions()
      .then((r) => {
        setVersions(r.versions);
        setVersion(r.versions[0] ?? "");
      })
      .catch(() => setVersions([]));
  }, []);

  const shape = useMemo(() => inspect(raw, format), [raw, format]);

  const loadSample = (id: string) => {
    const sample = SAMPLES.find((s) => s.id === id);
    if (!sample) return;
    setRaw(sample.body);
    setFormat(sample.format);
    setLoadedSample(sample.id);
    setError(null);
    textRef.current?.focus();
  };

  const ingestFile = async (file: File) => {
    const text = await file.text();
    setRaw(text);
    setFormat(file.name.endsWith(".json") ? "json" : "text");
    setLoadedSample(null);
    setError(null);
  };

  const run = useCallback(async () => {
    setError(null);

    if (!raw.trim()) {
      setError({
        title: "Nothing to verify",
        body: "Paste a log, drop a file, or load one of the sample batches above.",
      });
      return;
    }

    let payload: unknown = raw;
    if (format !== "text") {
      try {
        payload = JSON.parse(raw);
      } catch (e) {
        setError({
          title: "That is not valid JSON",
          body: `${(e as Error).message}. If this is an unstructured agent log, switch the format to Free text.`,
        });
        return;
      }
    }

    setBusy(true);
    try {
      const report = await verifyBatch({
        format,
        payload,
        rulepack_version: version || undefined,
      });
      router.push(`/reports/${report.id}`);
    } catch (e) {
      const err = e as ApiError;
      setError({
        title:
          err.status === 502
            ? "The parsing layer is unreachable"
            : err.status === 422
              ? "The payload was rejected"
              : err.status === 400
                ? "Bad request"
                : "Verification failed",
        body: err.detail ?? "Unknown error.",
      });
      setBusy(false);
    }
  }, [raw, format, version, router]);

  // Ctrl/Cmd+Enter submits from inside the textarea — this screen is used repeatedly.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !busy) {
        e.preventDefault();
        void run();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [run, busy]);

  const activeSample = SAMPLES.find((s) => s.id === loadedSample);

  return (
    <div className="space-y-4">
      <section aria-labelledby="samples-heading" className="card p-4">
        <h2 id="samples-heading" className="label">
          Load a sample batch
        </h2>
        <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {SAMPLES.map((s) => {
            const active = loadedSample === s.id;
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => loadSample(s.id)}
                aria-pressed={active}
                className={`card-interactive reveal rounded-md border p-3 text-left ${
                  active ? "border-line-strong bg-surface-2" : "border-line"
                } d-${(SAMPLES.indexOf(s) % 4) + 1}`}
                style={active ? { boxShadow: "0 0 0 3px var(--brand-soft)" } : undefined}
              >
                <span className="block text-sm font-medium text-body">
                  {s.label}
                </span>
                <span className="mt-1 block text-xs leading-relaxed text-muted">
                  {s.blurb}
                </span>
                <span className="clause mt-1.5 block">
                  {FORMAT_LABEL[s.format]}
                </span>
              </button>
            );
          })}
        </div>
        {activeSample && (
          <p className="mt-3 rounded-md bg-surface-2 px-3 py-2 text-xs leading-relaxed text-muted">
            <span className="font-medium text-body">Expect: </span>
            {activeSample.expect}
          </p>
        )}
      </section>

      <div className="card p-5">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
          <div>
            <div className="label mb-1.5">Format</div>
            <Segmented
              label="Payload format"
              value={format}
              onChange={(f) => {
                setFormat(f);
                setLoadedSample(null);
              }}
              options={[
                { value: "json", label: "JSON" },
                { value: "text", label: "Free text" },
                { value: "razorpay", label: "Razorpay" },
              ]}
            />
          </div>

          <div>
            <span className="label mb-1.5 block" id="rulepack-label">
              Rule-pack version
            </span>
            <Select
              id="rulepack"
              ariaLabel="Rule-pack version"
              className="w-48"
              value={version}
              onChange={setVersion}
              options={
                versions.length === 0
                  ? [{ value: "", label: "active" }]
                  : versions.map((v) => ({
                      value: v,
                      label: v,
                      hint: v === versions[0] ? "current" : undefined,
                    }))
              }
            />
          </div>

          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="btn"
            >
              Choose file
            </button>
            {raw && (
              <button
                type="button"
                onClick={() => {
                  setRaw("");
                  setLoadedSample(null);
                  setError(null);
                }}
                className="btn"
              >
                Clear
              </button>
            )}
            <button
              type="button"
              onClick={run}
              disabled={busy}
              className="btn-primary"
            >
              {busy ? "Verifying…" : "Run verification"}
              <span className="kbd ml-1 hidden sm:inline">⌘↵</span>
            </button>
          </div>
        </div>

        <p className="mt-3 text-xs leading-relaxed text-muted">
          {FORMAT_HELP[format]}
        </p>

        <input
          ref={fileRef}
          type="file"
          accept=".json,.txt"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void ingestFile(f);
          }}
        />

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const f = e.dataTransfer.files?.[0];
            if (f) void ingestFile(f);
          }}
          className={`mt-4 rounded-md border border-dashed transition-colors ${
            dragging ? "border-line-strong bg-surface-2" : "border-line"
          }`}
        >
          <label htmlFor="payload" className="sr-only">
            Agent log payload
          </label>
          <textarea
            id="payload"
            ref={textRef}
            value={raw}
            onChange={(e) => {
              setRaw(e.target.value);
              setLoadedSample(null);
            }}
            spellCheck={false}
            rows={16}
            placeholder={
              format === "text"
                ? "[14:00 IST] act_2 DEBIT mandate mdt_2002 cust cus_6002 amt Rs.4,999\n              pre-debit notice pushed 12:00 IST same day"
                : '[\n  {\n    "id": "a_001",\n    "type": "debit",\n    "timestamp": "2026-08-20T14:00:00+05:30",\n    "amount": 20000,\n    "afa_present": false\n  }\n]'
            }
            className="w-full resize-y bg-transparent p-4 font-mono text-xs leading-relaxed text-body outline-none placeholder:text-faint"
          />
        </div>

        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
          <span className="text-faint">
            Drop a <code className="font-mono">.json</code> or{" "}
            <code className="font-mono">.txt</code> file, or paste above.
          </span>
          {raw.trim() && (
            <span
              className={shape.ok ? "text-muted" : "text-fail-fg"}
              aria-live="polite"
            >
              {shape.ok ? `✓ ${shape.note}` : `✕ ${shape.note}`}
            </span>
          )}
        </div>
      </div>

      {busy && (
        <div
          aria-live="polite"
          className="rounded-md border border-line bg-surface px-4 py-3 text-sm text-muted"
        >
          {format === "text"
            ? "Parsing free-text log, then re-validating every extracted action…"
            : "Evaluating against the rule-pack…"}
        </div>
      )}

      {error && (
        <ErrorNote title={error.title}>
          {error.body}
          {error.title.includes("parsing layer") && (
            <p className="mt-2">
              Structured JSON bypasses the model entirely — switch the format to JSON and
              the verdicts are unaffected.
            </p>
          )}
        </ErrorNote>
      )}
    </div>
  );
}
