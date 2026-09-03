import type { Metadata, Viewport } from "next";
import { Open_Sans, Raleway } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/AppShell";
import { ServiceWorker } from "@/components/ServiceWorker";
import { Splash } from "@/components/Splash";

/**
 * Self-hosted at build time by next/font — no request to Google at runtime, and the
 * metrics-matched fallback means no layout shift as they swap in.
 *
 * Raleway sets headings, Open Sans carries body and UI. Monospace is untouched: clause
 * citations and rule ids stay mono on purpose (04-frontend.md §7 — it signals
 * "machine-checked, precise", which is the whole point of the citation).
 */
const openSans = Open_Sans({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
});

const raleway = Raleway({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-display",
});

export const metadata: Metadata = {
  // Social images are resolved against this. Without it Next falls back to localhost:3000
  // and every shared link previews a dead image once deployed, so it is set from the
  // environment with the dev origin as the fallback rather than left to warn on each build.
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  // Matches the tagline baked into the logo artwork. The PNG cannot be edited, so the
  // copy standardises on it rather than the other way round.
  title: "Rakshak — Compliance for AI payment agents",
  description:
    "Verifies autonomous payment-recovery agent actions against the RBI E-mandate Framework 2026 and NPCI mandate rules.",
  applicationName: "Rakshak",
  appleWebApp: {
    capable: true,
    title: "Rakshak",
    // "default" keeps the iOS status bar legible over our own light surfaces;
    // "black-translucent" would let content slide under the clock.
    statusBarStyle: "default",
  },
  formatDetection: { telephone: false },
};

/**
 * `viewportFit: "cover"` lets the app paint into the notch area — paired with the
 * safe-area padding in globals.css, so nothing important lands under a rounded corner.
 *
 * `maximumScale` is deliberately absent. Capping zoom is the classic PWA mistake: it
 * blocks pinch-zoom for anyone who needs it, and the iOS auto-zoom it is usually added to
 * prevent is fixed properly in CSS instead (16px inputs).
 */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#09090b" },
  ],
};

/**
 * Applied before first paint so an explicitly-chosen theme never flashes the wrong one.
 * It has to be inline and synchronous — a React effect runs too late to prevent the flash.
 */
const THEME_BOOTSTRAP = `
try {
  var t = localStorage.getItem('rakshak-theme');
  if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
} catch (e) {}
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${openSans.variable} ${raleway.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
        {/* Without JS the effect that dismisses the splash never runs, so it would sit
            over a perfectly usable page forever. <noscript> is the right lever here: a
            script-set class would also hide the splash during normal first paint. */}
        <noscript>
          <style>{`[data-splash]{display:none!important}`}</style>
        </noscript>
      </head>
      <body>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:border focus:border-line focus:bg-surface focus:px-3 focus:py-2 focus:text-sm"
        >
          Skip to content
        </a>
        <ServiceWorker />
        <Splash />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
