import type { Metadata, Viewport } from "next";

import "./globals.css";
import { labFonts } from "./lab-fonts";
import { Shell } from "@/components/shell";
import { TraceProvider } from "@/components/trace";

export const metadata: Metadata = {
  title: "StockSense - Hengtai Industrial Supply",
  description:
    "What to reorder, how much, and what it would cost to be wrong: eighteen thousand parts that mostly sell nothing, suppliers that run late and a Lunar New Year shutdown.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0a1220",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-product="stocksense" className={labFonts} suppressHydrationWarning>
      <body>
        <TraceProvider>
          <Shell>{children}</Shell>
        </TraceProvider>
      </body>
    </html>
  );
}
