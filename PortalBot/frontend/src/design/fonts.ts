/**
 * The suite's two faces, bundled with the product (no font service at run
 * time). Both are under the SIL Open Font License; the licences sit next to
 * the files in ./fonts.
 *
 *   Poppins        headings, big numbers and the interface
 *                  (300 light, 400, 500, 600 semibold, 700 bold)
 *   JetBrains Mono labels, part numbers, timestamps, formulas and money
 *                  columns that have to line up
 *
 * Put `fontVariables` on <html>; tokens.css picks the faces up from the
 * variables this file declares.
 */
import localFont from "next/font/local";

const poppins = localFont({
  src: [
    { path: "./fonts/poppins-300.woff2", weight: "300", style: "normal" },
    { path: "./fonts/poppins-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/poppins-500.woff2", weight: "500", style: "normal" },
    { path: "./fonts/poppins-600.woff2", weight: "600", style: "normal" },
    { path: "./fonts/poppins-700.woff2", weight: "700", style: "normal" },
  ],
  display: "swap",
  variable: "--ds-face-ui",
  fallback: ["ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
});

const mono = localFont({
  src: "./fonts/jetbrains-mono-variable.woff2",
  weight: "100 800",
  style: "normal",
  display: "swap",
  variable: "--ds-face-mono",
  fallback: ["ui-monospace", "Cascadia Mono", "Consolas", "monospace"],
});

export const fontVariables = `${poppins.variable} ${mono.variable}`;
