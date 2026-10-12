/**
 * LedgerFlow's own faces, bundled with the product (no font service at run
 * time; both under the SIL Open Font License, licences in src/fonts).
 *
 *   Archivo  headings, set narrow like the column heads of a bound ledger
 *   Inter    the interface
 *
 * Every figure is set in the suite's JetBrains Mono, tabular, so a money
 * column lines up the way a ledger column has to.
 */
import localFont from "next/font/local";

const archivo = localFont({
  src: "../fonts/archivo-variable.woff2",
  weight: "100 900",
  style: "normal",
  display: "swap",
  variable: "--lf-face-display",
  declarations: [{ prop: "font-stretch", value: "62% 125%" }],
  fallback: ["ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
});

const inter = localFont({
  src: "../fonts/inter-variable.woff2",
  weight: "100 900",
  style: "normal",
  display: "swap",
  variable: "--lf-face-ui",
  fallback: ["ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
});

export const ledgerFontVariables = `${archivo.variable} ${inter.variable}`;
