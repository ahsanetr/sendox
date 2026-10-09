import type { Metadata } from "next";
import { Archivo, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

import { AppFrame } from "@/components/app/app-frame";
import { SessionProvider } from "@/lib/session";

// Archivo is a grotesque with real tabular figures and holds up at the small
// sizes a data-dense product lives at — unlike the default UI sans everyone
// reaches for. Plex Mono appears only where a value genuinely is data: store
// domains, identifiers.
const archivo = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Sendox",
  description: "AI-native marketing for Shopify brands",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${archivo.variable} ${plexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <SessionProvider>
          <AppFrame>{children}</AppFrame>
        </SessionProvider>
      </body>
    </html>
  );
}
