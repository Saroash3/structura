"use client";

import { useRef } from "react";
import { motion } from "motion/react";
import { useReached } from "@/lib/use-reached";

/** Fade-up once the element is reached (or scrolled past), with an optional stagger delay. */
export function ScrollReveal({ children, delay = 0, className }: { children: React.ReactNode; delay?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const reached = useReached(ref);
  return (
    <motion.div ref={ref} className={className} initial={{ opacity: 0, y: 18 }} animate={reached ? { opacity: 1, y: 0 } : undefined}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}>
      {children}
    </motion.div>
  );
}

/** Eyebrow + title + lead paragraph used at the top of every landing section. */
export function SectionHeading({ eyebrow, title, lead, id }: { eyebrow: string; title: string; lead?: string; id: string }) {
  return (
    <ScrollReveal className="max-w-2xl">
      <p className="eyebrow mb-4"><span className="h-px w-6 bg-accent" aria-hidden />{eyebrow}</p>
      <h2 id={id} className="text-title">{title}</h2>
      {lead && <p className="mt-4 text-lg leading-relaxed text-muted">{lead}</p>}
    </ScrollReveal>
  );
}
