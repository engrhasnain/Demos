import type { Metadata, Viewport } from "next";

import "./globals.css";
import { fontVariables } from "@/design/fonts";
import { nunito } from "@/components/face";
import { PwaRegister } from "@/components/pwa";
import { Shell } from "@/components/shell";
import { TraceProvider } from "@/components/trace";

export const metadata: Metadata = {
  title: "FrontDesk - Hengtai Industrial Supply",
  description:
    "Answers the questions customers actually ask, from live records, for the right customer only, around the clock on the website and on LINE.",
  applicationName: "FrontDesk",
  appleWebApp: { capable: true, title: "FrontDesk", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#fff1ea",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-product="frontdeskai" className={`${fontVariables} ${nunito.variable}`} suppressHydrationWarning>
      <body>
        <TraceProvider>
          <Shell>{children}</Shell>
        </TraceProvider>
        <PwaRegister />
      </body>
    </html>
  );
}
