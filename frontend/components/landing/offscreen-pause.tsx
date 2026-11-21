"use client";

import { useRef } from "react";
import { useInView } from "motion/react";

/**
 * Wraps content and marks it `data-offscreen="true"` while it is out of view, which pauses every
 * CSS animation inside it (see globals.css). Used for the marquee so it does not run while offscreen.
 */
export function OffscreenPause({ children, className }: { children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { margin: "100px" });
  return (
    <div ref={ref} className={className} data-offscreen={inView ? undefined : "true"} aria-hidden>
      {children}
    </div>
  );
}
