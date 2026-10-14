/**
 * FrontDesk's own face: Nunito, rounded and warm, for a product that talks to
 * customers. Bundled with the product from the open-licensed package, so
 * nothing is fetched at run time. The suite's mono stays for labels and data.
 */
import localFont from "next/font/local";

export const nunito = localFont({
  src: [
    {
      path: "../../node_modules/@fontsource-variable/nunito/files/nunito-latin-wght-normal.woff2",
      weight: "200 1000",
      style: "normal",
    },
  ],
  display: "swap",
  variable: "--fd-face",
  fallback: ["ui-rounded", "system-ui", "Segoe UI", "sans-serif"],
});
