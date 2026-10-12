import type { Metadata, Viewport } from "next";

import "./globals.css";
import { fontVariables } from "@/design/fonts";
import { Shell } from "@/components/shell";
import { TraceProvider } from "@/components/trace";

export const metadata: Metadata = {
  title: "QuoteAgent - Hengtai Industrial Supply",
  description:
    "Takes a messy, multi-line request for quotation from the inbox to an approved quote the same day.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0b0d12",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-product="quoteagent" className={fontVariables} suppressHydrationWarning>
      <body>
        <TraceProvider>
          <Shell>{children}</Shell>
        </TraceProvider>
      </body>
    </html>
  );
}
