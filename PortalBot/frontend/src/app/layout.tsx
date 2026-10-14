import type { Metadata, Viewport } from "next";

import "./globals.css";
import { fontVariables } from "@/design/fonts";
import { Shell } from "@/components/shell";
import { TraceProvider } from "@/components/trace";

export const metadata: Metadata = {
  title: "PortalBot - Hengtai Industrial Supply",
  description:
    "Books every shipment in the carrier portal and writes the tracking number back into the order screen, without duplicates, resuming cleanly after a crash, and stopping when a screen it drives has changed.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0d1b1b",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-product="portalbot" className={fontVariables} suppressHydrationWarning>
      <body>
        <TraceProvider>
          <Shell>{children}</Shell>
        </TraceProvider>
      </body>
    </html>
  );
}
