import { UploadPanel } from "@/components/UploadPanel";

export const metadata = { title: "Verify — Rakshak" };

export default function VerifyPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">Verify an agent log</h1>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted">
          Submit a payment-recovery agent&apos;s proposed actions. Each one is checked
          against the versioned rule-pack, and every failure is cited to its clause and
          source circular.
        </p>
      </div>

      <UploadPanel />
    </div>
  );
}
