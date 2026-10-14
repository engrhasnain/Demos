/**
 * OpsAgent's two faces, bundled with the product (no font service at run
 * time). Both are under the SIL Open Font License; the licences sit next to
 * the files in ./fonts.
 *
 *   Space Grotesk  headings, big numbers and the interface: a command-centre
 *                  face, squarer than the rest of the suite
 *   IBM Plex Mono  labels, timestamps, queries and anything that has to line up
 *
 * Put `fontVariables` on <html>; tokens.css picks the faces up from the
 * variables this file declares.
 */
import localFont from "next/font/local";

const grotesk = localFont({
  src: "./fonts/space-grotesk-variable.woff2",
  weight: "300 700",
  style: "normal",
  display: "swap",
  variable: "--ds-face-ui",
  fallback: ["ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
});

const mono = localFont({
  src: [
    { path: "./fonts/ibm-plex-mono-400.woff2", weight: "400", style: "normal" },
    { path: "./fonts/ibm-plex-mono-500.woff2", weight: "500", style: "normal" },
    { path: "./fonts/ibm-plex-mono-600.woff2", weight: "600", style: "normal" },
  ],
  display: "swap",
  variable: "--ds-face-mono",
  fallback: ["ui-monospace", "Cascadia Mono", "Consolas", "monospace"],
});

export const fontVariables = `${grotesk.variable} ${mono.variable}`;
