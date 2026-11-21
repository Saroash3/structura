"use client";

import { useRef } from "react";
import { ListChecks, Mic, Play, ShieldCheck, Sparkles, type LucideIcon } from "lucide-react";
import { AnimatedBeam } from "@/components/ui/animated-beam";
import { ScrollReveal, SectionHeading } from "@/components/landing/scroll-reveal";

const STEPS: { icon: LucideIcon; title: string; text: string; tag: string }[] = [
  { icon: Sparkles, title: "Plan", tag: "Gemini", text: "Your question becomes a plan made only of operations, like enqueue(5). The model never draws a state." },
  { icon: ShieldCheck, title: "Verify", tag: "Python", text: "Every operation runs on a real data structure. Each narrated fact is checked against the true state." },
  { icon: Mic, title: "Narrate", tag: "Piper, local", text: "Every scene is spoken on your machine. No cloud voice, and audio is cached per sentence." },
  { icon: Play, title: "Animate", tag: "Motion", text: "Frames are drawn from the true state, and each one lasts exactly as long as its narration." },
  { icon: ListChecks, title: "Quiz", tag: "Computed", text: "Three questions whose answers come from running the real structure, never from the model." },
];

export function HowItWorks() {
  const container = useRef<HTMLDivElement>(null);
  const r0 = useRef<HTMLDivElement>(null), r1 = useRef<HTMLDivElement>(null), r2 = useRef<HTMLDivElement>(null),
    r3 = useRef<HTMLDivElement>(null), r4 = useRef<HTMLDivElement>(null);
  const beam = { containerRef: container, duration: 4, pathColor: "#404040", pathOpacity: 0.9, pathWidth: 2, gradientStartColor: "#FF7A1A", gradientStopColor: "#4CC9F0" };

  return (
    <section id="how" aria-labelledby="how-title" className="section-y scroll-mt-20 border-t border-border">
      <div className="container-page">
        <SectionHeading id="how-title" eyebrow="How it works" title="One pipeline. The AI only gets the first step."
          lead="A lesson passes through five stages before you see it. Everything after the plan is deterministic code you can test." />

        <div ref={container} className="relative mt-16">
          {/* beams sit behind the step nodes and connect them in order */}
          <AnimatedBeam {...beam} fromRef={r0} toRef={r1} delay={0} />
          <AnimatedBeam {...beam} fromRef={r1} toRef={r2} delay={0.4} />
          <AnimatedBeam {...beam} fromRef={r2} toRef={r3} delay={0.8} />
          <AnimatedBeam {...beam} fromRef={r3} toRef={r4} delay={1.2} />
          <ol className="relative grid gap-5 lg:grid-cols-5 lg:gap-4">
            {STEPS.map(({ icon: Icon, title, text, tag }, i) => (
              <li key={title}>
                <ScrollReveal delay={i * 0.09} className="group flex h-full gap-4 lg:flex-col lg:items-center lg:gap-6">
                  {/* the node sits outside the card so the beams run through open space */}
                  <div ref={i === 0 ? r0 : i === 1 ? r1 : i === 2 ? r2 : i === 3 ? r3 : r4}
                    className="relative z-10 grid size-14 shrink-0 place-items-center rounded-2xl border border-border bg-background transition-[transform,border-color,box-shadow] duration-300 group-hover:-translate-y-1 group-hover:border-accent group-hover:shadow-[0_0_24px_-4px_rgba(255,122,26,0.45)]">
                    <Icon className="size-6 text-accent transition-transform duration-300 group-hover:scale-110 group-hover:-rotate-6" aria-hidden />
                  </div>
                  <div className="flex-1 rounded-2xl border border-border bg-surface p-5 transition-[transform,border-color] duration-300 group-hover:-translate-y-1 group-hover:border-accent/50 lg:w-full">
                    <div className="mb-2 flex items-center gap-2">
                      <span className="font-mono text-xs text-muted">0{i + 1}</span>
                      <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted">{tag}</span>
                    </div>
                    <h3 className="text-lg font-semibold">{title}</h3>
                    <p className="mt-1.5 text-[15px] leading-relaxed text-muted">{text}</p>
                  </div>
                </ScrollReveal>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
