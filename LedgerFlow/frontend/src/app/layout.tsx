import type { Metadata, Viewport } from "next";

import "./globals.css";
import { fontVariables } from "@/design/fonts";
import { ledgerFontVariables } from "./ledger-fonts";
import { Shell } from "@/components/shell";
import { TraceProvider } from "@/components/trace";

export const metadata: Metadata = {
  title: "LedgerFlow - Hengtai Industrial Supply",
  description:
    "Supplier invoices read, matched three ways against the purchase order and the delivery, and posted to the ledger once.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#06140f",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-product="ledgerflow" className={`${fontVariables} ${ledgerFontVariables}`} suppressHydrationWarning>
      <body>
        <TraceProvider>
          <Shell>{children}</Shell>
        </TraceProvider>
      </body>
    </html>
  );
}
