import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { AppFrame } from "@/components/app/app-frame";
import { SessionProvider } from "@/lib/session";

const sans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
  fallback: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
});

const mono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
});

/** Applied before React hydrates, so a remembered scheme never flashes the
 *  default on its way in. Inlined deliberately: a separate request would land
 *  after first paint, which is the whole problem. */
const APPLY_SCHEME = `try{var s=localStorage.getItem("sendox.scheme");if(s&&["swiss","graphite","indigo","teal","midnight"].indexOf(s)>-1)document.documentElement.dataset.scheme=s}catch(e){}`;

export const metadata: Metadata = {
  title: "Sendox",
  description: "AI-native marketing for Shopify brands",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${sans.variable} ${mono.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: APPLY_SCHEME }} />
      </head>
      <body className="min-h-full flex flex-col">
        <SessionProvider>
          <AppFrame>{children}</AppFrame>
        </SessionProvider>
      </body>
    </html>
  );
}
