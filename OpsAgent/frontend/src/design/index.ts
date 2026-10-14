/**
 * Hengtai design system.
 *
 * Copy this whole folder into a product's src/, import tokens.css and
 * components.css from its globals.css, put `fontVariables` (from ./fonts,
 * imported only in the root layout) on <html>, and set
 * its accent (data-product on <html>, or the accent block in tokens.css).
 * See docs/design-system.md.
 */

export { Band, Banner, Button, Card, Empty, Eyebrow, LinkButton, Spinner, Stamp, Stat } from "./Surface";
export type { ButtonTone } from "./Surface";
export { Constellation } from "./Constellation";
export type {
  ConstellationHandle,
  ConstellationLink,
  ConstellationNode,
  PulseOptions,
  Tone,
} from "./Constellation";
export { CountUp } from "./CountUp";
export { LiveFeedCard } from "./LiveFeedCard";
export type { FeedItem } from "./LiveFeedCard";
export { Meter } from "./Meter";
export { NodeChain } from "./NodeChain";
export type { ChainItem } from "./NodeChain";
export { Reveal } from "./Reveal";
export { ScrollHeader, ScrollProgressBar } from "./ScrollHeader";
export type { NavItem } from "./ScrollHeader";
export { LiveDot, StatusChip } from "./StatusChip";
export type { ChipTone } from "./StatusChip";
export { StepRail } from "./StepRail";
export type { RailStep } from "./StepRail";
export { Tabs } from "./Tabs";
export type { TabItem } from "./Tabs";
export { TraceSheet, TraceSteps } from "./TraceSheet";
export type { TraceInputView, TraceStepView } from "./TraceSheet";
export {
  EASE_OUT,
  REVEAL_MS,
  STAGGER_MS,
  easeOutExpo,
  prefersReducedMotion,
  useInView,
  usePageVisible,
  useReducedMotion,
  useScrollProgress,
} from "./motion";
