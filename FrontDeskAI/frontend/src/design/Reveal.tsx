"use client";

/**
 * Reveal on view.
 *
 * The element starts transparent and 32 px low, and rises into place with
 * expo-out when it scrolls into view. `index` staggers siblings by 70 ms.
 * Under reduced motion it is simply there. The styling lives in
 * components.css (.ds-reveal), so the same class works on a table row.
 */

import { createElement, type CSSProperties, type ReactNode } from "react";

import { useInView } from "./motion";

type RevealProps = {
  children?: ReactNode;
  as?: keyof React.JSX.IntrinsicElements;
  index?: number;
  /** Extra delay in milliseconds, on top of the stagger. */
  delay?: number;
  /** Travel in pixels (24 to 40 in this suite). */
  y?: number;
  /** "rise" (default), "left" (slides in from the left), "scale" (grows). */
  from?: "rise" | "left" | "scale";
  className?: string;
  style?: CSSProperties;
  onClick?: () => void;
  [attribute: `data-${string}`]: string | undefined;
} & Omit<React.HTMLAttributes<HTMLElement>, "children" | "className" | "style" | "onClick">;

export function Reveal({
  children,
  as = "div",
  index = 0,
  delay = 0,
  y,
  from = "rise",
  className = "",
  style,
  ...rest
}: RevealProps) {
  const [ref, shown] = useInView<HTMLElement>();
  const stagger = (index % 10) * 70 + delay;
  return createElement(
    as,
    {
      ref,
      className: `ds-reveal ${className}`,
      "data-shown": shown ? "" : undefined,
      "data-from": from,
      style: {
        ...style,
        "--ds-d": `${stagger}ms`,
        ...(y !== undefined ? { "--ds-reveal-y": `${y}px` } : {}),
      } as CSSProperties,
      ...rest,
    },
    children,
  );
}
