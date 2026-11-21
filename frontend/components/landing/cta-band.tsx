"use client";

import { useRef } from "react";
import Link from "next/link";
import { motion, useInView, useReducedMotion, useSpring } from "motion/react";
import { ArrowRight } from "lucide-react";
import { DotPattern } from "@/components/ui/dot-pattern";
import { ScrollReveal } from "@/components/landing/scroll-reveal";

/** Primary button that leans toward the cursor (off for touch and reduced motion). */
function MagneticLink({ href, children }: { href: string; children: React.ReactNode }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLAnchorElement>(null);
  const x = useSpring(0, { stiffness: 220, damping: 15, mass: 0.4 });
  const y = useSpring(0, { stiffness: 220, damping: 15, mass: 0.4 });
  return (
    <motion.span style={{ x, y }} className="inline-block">
      <Link ref={ref} href={href}
        onPointerMove={(e) => {
          if (reduce || e.pointerType !== "mouse" || !ref.current) return;
          const r = ref.current.getBoundingClientRect();
          x.set((e.clientX - (r.left + r.width / 2)) * 0.3);
          y.set((e.clientY - (r.top + r.height / 2)) * 0.4);
        }}
        onPointerLeave={() => { x.set(0); y.set(0); }}
        className="group inline-flex h-14 items-center gap-2.5 rounded-2xl bg-accent px-8 text-lg font-semibold text-on-accent shadow-[0_10px_40px_-10px_rgba(255,122,26,0.6)] transition-[background-color,transform] hover:bg-accent/95 active:scale-[0.97]">
        {children}
        <ArrowRight className="size-5 transition-transform group-hover:translate-x-1" aria-hidden />
      </Link>
    </motion.span>
  );
}

export function CtaBand() {
  const reduce = useReducedMotion();
  const boxRef = useRef<HTMLDivElement>(null);
  const onScreen = useInView(boxRef, { margin: "100px" });
  return (
    <section aria-labelledby="cta-title" className="section-y border-t border-border">
      <div className="container-page">
        <ScrollReveal>
          <div ref={boxRef} className="relative isolate overflow-hidden rounded-3xl border border-border bg-surface px-6 py-16 text-center sm:px-12 sm:py-20">
            {/* subtle background: dots that drift only while on screen, under a static glow */}
            <motion.div aria-hidden className="absolute inset-0 -z-10"
              animate={reduce || !onScreen ? undefined : { x: [0, -22, 0], y: [0, -22, 0] }} transition={{ duration: 18, repeat: Infinity, ease: "linear" }}>
              <DotPattern width={22} height={22} cr={1} className="text-border [mask-image:radial-gradient(ellipse_at_center,black_20%,transparent_70%)]" />
            </motion.div>
            {/* static glow: animating a large blurred layer repaints it every frame */}
            <div aria-hidden className="absolute top-1/2 left-1/2 -z-10 size-[28rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-accent/10 blur-2xl" />
            <p className="eyebrow mb-5 justify-center">Free to use</p>
            <h2 id="cta-title" className="text-title mx-auto max-w-2xl">Ready to watch a structure move?</h2>
            <p className="mx-auto mt-4 max-w-xl text-lg text-muted">
              Create an account to save lessons, reopen them without regenerating, and track your quiz scores.
            </p>
            <div className="mt-10 flex flex-col items-center justify-center gap-4 sm:flex-row">
              <MagneticLink href="/signup">Create your account</MagneticLink>
              <Link href="/login" className="text-sm font-medium text-muted underline-offset-4 transition-colors hover:text-text hover:underline">
                I already have an account
              </Link>
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
