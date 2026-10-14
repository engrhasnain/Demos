import type { Metadata, Viewport } from "next";

import "./globals.css";
import { fontVariables } from "@/design/fonts";
import { Shell } from "@/components/shell";
import { TraceProvider } from "@/components/trace";

export const metadata: Metadata = {
  title: "OpsAgent - Hengtai Industrial Supply",
  description:
    "Questions about the business, answered from reviewed queries, scoped to what the asker may see, with the working shown.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0d1b1b",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-product="opsagent" className={fontVariables} suppressHydrationWarning>
      <body>
        <TraceProvider>
          <Shell>{children}</Shell>
        </TraceProvider>
      </body>
    </html>
  );
}
