import type { MetadataRoute } from "next";

/**
 * Web app manifest — Next.js serves this at /manifest.webmanifest.
 *
 * `display: "standalone"` rather than `fullscreen`: this is a tool people read alongside
 * other things, and swallowing the status bar on a phone hides the clock and battery for no
 * benefit. Portrait is not locked either — the action table and the timeline are genuinely
 * better in landscape on a phone.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Rakshak — Compliance for AI payment agents",
    short_name: "Rakshak",
    description:
      "Checks what an autonomous payment-recovery agent proposes to do against the RBI E-mandate Framework 2026, and cites the clause it breaks.",
    id: "/",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "any",
    background_color: "#070707",
    theme_color: "#070707",
    categories: ["business", "finance", "productivity"],
    icons: [
      { src: "/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      {
        src: "/icon-maskable-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "maskable",
      },
      {
        src: "/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
    shortcuts: [
      {
        name: "Verify an agent log",
        short_name: "Verify",
        url: "/verify",
        icons: [{ src: "/icon-192.png", sizes: "192x192" }],
      },
      {
        name: "Rule-pack",
        short_name: "Rules",
        url: "/rules",
        icons: [{ src: "/icon-192.png", sizes: "192x192" }],
      },
    ],
  };
}
