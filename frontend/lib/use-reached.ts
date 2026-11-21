"use client";

import { useEffect, useState, type RefObject } from "react";

/**
 * True once the element's top has entered the viewport OR been scrolled past.
 * Unlike a plain IntersectionObserver, a fast jump (anchor link, page-down) that skips over the
 * element still counts, so scroll-revealed content can never stay hidden.
 */
export function useReached(ref: RefObject<Element | null>, threshold = 0.9): boolean {
  const [reached, setReached] = useState(false);
  useEffect(() => {
    if (reached) return;
    const check = () => {
      const el = ref.current;
      if (el && el.getBoundingClientRect().top < window.innerHeight * threshold) setReached(true);
    };
    check();
    window.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    return () => {
      window.removeEventListener("scroll", check);
      window.removeEventListener("resize", check);
    };
  }, [reached, ref, threshold]);
  return reached;
}
