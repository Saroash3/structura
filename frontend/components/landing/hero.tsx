"use client";

import { useCallback, useRef, useState } from "react";
import Link from "next/link";
import { motion, useInView, useMotionTemplate, useMotionValue, useReducedMotion } from "motion/react";
import { ArrowRight, BadgeCheck, Cpu } from "lucide-react";
import { AnimatedShinyText } from "@/components/ui/animated-shiny-text";
import { BlurFade } from "@/components/ui/blur-fade";
import { DotPattern } from "@/components/ui/dot-pattern";
import { Spotlight } from "@/components/ui/spotlight-new";
import { LiveDemo } from "@/components/landing/live-demo";
import { cn } from "@/lib/utils";

const WORDS = ["Watch", "data", "structures", "move,", "step", "by", "step."];
const ORANGE = (a: number) => `rgba(255, 122, 26, ${a})`;

function Headline() {
  return (
    <h1 className="text-display">
      {WORDS.map((w, i) => (
        <BlurFade key={i} delay={0.08 + i * 0.07} duration={0.5} offset={10} direction="up" blur="10px" className="mr-[0.22em] inline-block">
          {w === "move," ? (
            <span className="relative inline-block">
              move<span className="text-accent">,</span>
              <motion.span aria-hidden className="absolute inset-x-0 -bottom-[0.06em] h-[0.09em] origin-left rounded-full bg-accent"
                initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ delay: 0.75, duration: 0.7, ease: [0.22, 1, 0.36, 1] }} />
            </span>
          ) : w}
        </BlurFade>
      ))}
    </h1>
  );
}

/** Small label floating next to the demo. It bobs only while the hero is on screen. */
function FloatingChip({ className, delay, run, children }: { className: string; delay: number; run: boolean; children: React.ReactNode }) {
  return (
    <motion.div aria-hidden initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1, y: run ? [0, -6, 0] : 0 }}
      transition={{ opacity: { delay }, scale: { delay, type: "spring" }, y: run ? { delay, duration: 4, repeat: Infinity, ease: "easeInOut" } : { duration: 0.2 } }}
      className={cn("absolute z-10 hidden items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-xs shadow-md sm:inline-flex", className)}>
      {children}
    </motion.div>
  );
}

export function Hero() {
  const reduce = useReducedMotion();
  const mx = useMotionValue(-1000);
  const my = useMotionValue(-1000);
  const glow = useMotionTemplate`radial-gradient(520px circle at ${mx}px ${my}px, ${ORANGE(0.09)}, transparent 65%)`;
  const [step, setStep] = useState({ n: 1, total: 5 });
  const onStep = useCallback((n: number, total: number) => setStep({ n, total }), []);
  const sectionRef = useRef<HTMLElement>(null);
  const onScreen = useInView(sectionRef, { margin: "100px" }); // loops pause once the hero scrolls away

  return (
    <section
      ref={sectionRef}
      data-offscreen={onScreen ? undefined : "true"}
      className="relative isolate overflow-hidden"
      onPointerMove={(e) => {
        if (reduce || e.pointerType !== "mouse") return;
        const r = e.currentTarget.getBoundingClientRect();
        mx.set(e.clientX - r.left);
        my.set(e.clientY - r.top);
      }}>
      {/* background: dots fading out, an ambient orange spotlight, and a glow that follows the cursor */}
      <DotPattern width={22} height={22} cr={1.1}
        className="-z-10 text-border [mask-image:radial-gradient(ellipse_70%_60%_at_50%_35%,black,transparent)]" />
      <div className="pointer-events-none absolute inset-0 -z-10 hidden md:block" aria-hidden>
        {onScreen && <Spotlight
          gradientFirst={`radial-gradient(68.54% 68.72% at 55.02% 31.46%, ${ORANGE(0.08)} 0, ${ORANGE(0.02)} 50%, transparent 80%)`}
          gradientSecond={`radial-gradient(50% 50% at 50% 50%, ${ORANGE(0.05)} 0, ${ORANGE(0.015)} 80%, transparent 100%)`}
          gradientThird={`radial-gradient(50% 50% at 50% 50%, ${ORANGE(0.04)} 0, ${ORANGE(0.01)} 80%, transparent 100%)`}
          duration={10} />}
      </div>
      <motion.div aria-hidden className="pointer-events-none absolute inset-0 -z-10" style={{ background: glow }} />

      <div className="container-page grid items-center gap-14 pt-12 pb-20 sm:pt-16 lg:grid-cols-[1.05fr_1fr] lg:gap-12 lg:pt-24 lg:pb-28">
        <div>
          <BlurFade delay={0} duration={0.4}>
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-border bg-surface/60 px-3.5 py-1.5 text-xs backdrop-blur">
              <BadgeCheck className="size-3.5 text-accent2" aria-hidden />
              <AnimatedShinyText className="mx-0 max-w-none text-muted">Every step verified by real code</AnimatedShinyText>
            </div>
          </BlurFade>
          <Headline />
          <BlurFade delay={0.6} duration={0.5}>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted">
              Ask about a data structure and get an animated, narrated lesson with a short quiz. The AI only plans the operations.
              Real code computes every state, and every sentence is fact-checked before you hear it.
            </p>
          </BlurFade>
          <BlurFade delay={0.72} duration={0.5}>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <Link href="/signup"
                className="group inline-flex h-12 items-center gap-2 rounded-xl bg-accent px-6 text-base font-semibold text-on-accent shadow-[0_0_0_0_rgba(255,122,26,0)] transition-[transform,box-shadow,background-color] hover:-translate-y-0.5 hover:bg-accent/95 hover:shadow-[0_8px_30px_-6px_rgba(255,122,26,0.55)] active:translate-y-0 active:scale-[0.97]">
                Get started
                <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" aria-hidden />
              </Link>
              <a href="#how"
                className="inline-flex h-12 items-center rounded-xl border border-border bg-surface/50 px-6 text-base font-medium transition-[transform,border-color,color] hover:-translate-y-0.5 hover:border-accent2 hover:text-accent2 active:translate-y-0 active:scale-[0.97]">
                See how it works
              </a>
            </div>
            <p className="mt-6 inline-flex items-center gap-2 text-sm text-muted">
              <Cpu className="size-4" aria-hidden /> Everything except the Gemini call runs locally.
            </p>
          </BlurFade>
        </div>

        <BlurFade delay={0.35} duration={0.6} offset={16} className="relative lg:pl-4">
          <FloatingChip delay={1.1} run={onScreen} className="-top-4 left-2 lg:-left-3">
            <span className="relative flex size-2">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-accent" />
            </span>
            Live lesson: queue, step <span className="tabular-nums">{step.n}</span> of {step.total}
          </FloatingChip>
          <FloatingChip delay={1.3} run={onScreen} className="-right-2 -bottom-4 lg:-right-4">
            <BadgeCheck className="size-3.5 text-accent2" /> Verified by real code
          </FloatingChip>
          <LiveDemo onStep={onStep} />
        </BlurFade>
      </div>
    </section>
  );
}
