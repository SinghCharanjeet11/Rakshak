export const metadata = { title: "Offline — Rakshak" };

/**
 * Served by the service worker when a navigation fails with no cached copy.
 *
 * It says "nothing was checked", never "everything is fine". An offline compliance tool
 * that implies a clean result is worse than one that plainly refuses.
 */
export default function OfflinePage() {
  return (
    <div className="mx-auto max-w-xl py-16 text-center">
      <h1 className="text-lg font-semibold tracking-tight">You are offline</h1>
      <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-muted">
        Rakshak needs its backend to verify anything, and verdicts are never served from
        cache — a stale compliance report is worse than none.
      </p>
      <p className="mx-auto mt-4 max-w-md text-xs leading-relaxed text-faint">
        Nothing has been checked and nothing has passed. Reconnect and run the verification
        again; stored reports will load as soon as the API is reachable.
      </p>
      <a href="/" className="btn-primary mt-6 inline-flex">
        Try again
      </a>
    </div>
  );
}
