"use client";

import { NumberTicker } from "@/components/ui/number-ticker";
import { FACTS } from "@/lib/facts";

const STATS = [
  { value: FACTS.structures, suffix: "", label: "data structures and algorithms you can watch" },
  { value: FACTS.verifiedPercent, suffix: "%", label: "of narrated scenes checked against the true state" },
  { value: FACTS.quizQuestions, suffix: "", label: "quiz questions per lesson, answers computed by code" },
  { value: FACTS.minLessonSeconds, suffix: "s", label: "minimum lesson length, narrated locally by Piper" },
];

export function StatStrip() {
  return (
    <section aria-label="Structura in numbers" className="border-y border-border bg-surface/40">
      <dl className="container-page grid grid-cols-2 lg:grid-cols-4">
        {STATS.map((s, i) => (
          <div key={s.label}
            className={`flex flex-col gap-1.5 px-2 py-8 sm:px-6 lg:py-10 ${i % 2 === 1 ? "border-l border-border" : ""} ${i >= 2 ? "border-t border-border lg:border-t-0" : ""} ${i === 2 ? "lg:border-l" : ""}`}>
            <dt className="order-2 text-sm leading-snug text-muted">{s.label}</dt>
            <dd className="order-1 font-heading text-4xl font-semibold tracking-tight text-text sm:text-5xl">
              <NumberTicker value={s.value} delay={0.1 * i} />
              <span className="text-accent">{s.suffix}</span>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
