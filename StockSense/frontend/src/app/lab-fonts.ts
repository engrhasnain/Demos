/**
 * StockSense's own faces: a technical grotesk for the interface and its
 * mono for every readout, part number and formula. Fetched and bundled at
 * build time by next/font, so nothing is loaded from a font service when
 * the product runs. They feed the suite's font variables, so the shared
 * components pick them up unchanged.
 */
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
  display: "swap",
  variable: "--ds-face-ui",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--ds-face-mono",
});

export const labFonts = `${sans.variable} ${mono.variable}`;
