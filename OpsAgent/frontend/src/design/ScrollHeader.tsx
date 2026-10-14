"use client";

/**
 * ScrollHeader - the suite's sticky header.
 *
 * Sits on the ink band (with an optional thin strip above it for a notice).
 * Transparent at the top of the page, solid ink with a
 * hairline once anything is scrolled, and an accent bar along its bottom edge
 * that fills with the scroll position (transform: scaleX, nothing else). Below
 * 1080 px the navigation folds into a menu button that opens a solid ink
 * sheet; Escape closes it and focus returns to the button.
 */

import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { useScrollProgress } from "./motion";

export type NavItem = { href: string; label: string; active?: boolean };

export function ScrollProgressBar() {
  const { progress } = useScrollProgress();
  return (
    <span className="ds-scroll-progress" aria-hidden>
      <span style={{ transform: `scaleX(${progress})` }} />
    </span>
  );
}

export function ScrollHeader({
  brand,
  nav,
  status,
  actions,
  menuFooter,
  topLine,
}: {
  brand: ReactNode;
  nav: NavItem[];
  status?: ReactNode;
  actions?: ReactNode;
  menuFooter?: ReactNode;
  /** An optional thin strip above the header, for a notice. Set --ds-header-top to its height. */
  topLine?: ReactNode;
}) {
  const { progress, scrolled } = useScrollProgress();
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <header className="ds-header" data-solid={scrolled || open ? "" : undefined}>
      {topLine && (
        <div className="ds-header-top">
          <div className="ds-header-top-inner">{topLine}</div>
        </div>
      )}
      <div className="ds-header-inner">
        <div className="ds-header-brand">{brand}</div>

        <nav className="ds-header-nav" aria-label="Main">
          {nav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="ds-nav-link"
              aria-current={item.active ? "page" : undefined}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="ds-header-right">
          {status && <div className="ds-header-status">{status}</div>}
          {actions}
          <button
            ref={button}
            type="button"
            className="ds-menu-button"
            aria-expanded={open}
            aria-controls="ds-menu-sheet"
            onClick={() => setOpen((value) => !value)}
          >
            <span className="ds-menu-icon" data-open={open ? "" : undefined} aria-hidden>
              <i />
              <i />
            </span>
            {open ? "Close" : "Menu"}
          </button>
        </div>
      </div>

      <span className="ds-scroll-progress" aria-hidden>
        <span style={{ transform: `scaleX(${progress})` }} />
      </span>

      {open && (
        <div id="ds-menu-sheet" className="ds-menu-sheet">
          <nav aria-label="Main" className="ds-menu-nav">
            {nav.map((item, index) => (
              <Link
                key={item.href}
                href={item.href}
                className="ds-menu-link"
                aria-current={item.active ? "page" : undefined}
                style={{ "--ds-d": `${index * 50}ms` } as React.CSSProperties}
                onClick={() => setOpen(false)}
              >
                <span className="ds-menu-index">{String(index + 1).padStart(2, "0")}</span>
                {item.label}
              </Link>
            ))}
          </nav>
          {menuFooter && <div className="ds-menu-footer">{menuFooter}</div>}
        </div>
      )}
    </header>
  );
}
