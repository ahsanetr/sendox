import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Cache Components and Partial Prefetching are both off deliberately.
  //
  // They exist to let Next prerender a static shell per route and stream the
  // dynamic parts in. Every page in this app is a "use client" module whose
  // content comes from a polled API call behind a session cookie, so there is
  // no static shell to prerender: Next dropped each segment from the render
  // and the dev overlay threw a full-page error over the app on every load —
  // which also swallowed clicks on the rail. The documented per-segment
  // escape, `export const instant = false`, is a server-only route config and
  // Next refuses it in a client module, so the choice is the whole flag.
  //
  // Turn both on once pages have server-rendered shells worth prefetching.
  // That is the real fix; this is the honest state of things until then.

  // The dev badge defaults to the bottom-left corner, which is where the rail
  // keeps the account row and the scheme picker — it sat on top of them.
  devIndicators: { position: "bottom-right" },

  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
