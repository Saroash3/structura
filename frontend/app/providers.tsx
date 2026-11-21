"use client";

import { MotionConfig } from "motion/react";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * App-wide client providers.
 * - MotionConfig reducedMotion="user": every Motion animation respects prefers-reduced-motion.
 * Scrolling is the browser's own (no smooth-scroll library); in-page links use CSS scroll-behavior.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <TooltipProvider delay={200}>{children}</TooltipProvider>
    </MotionConfig>
  );
}
