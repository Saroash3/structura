"use client";

import { motion } from "motion/react";
import type { QuizRow } from "@/lib/data";
import { useMounted } from "@/lib/use-mounted";
import { structureLabel } from "@/lib/structure-labels";

/** Date shown after mount so server and client markup match (locale and time zone differ). */
function LocalDate({ iso }: { iso: string }) {
  const mounted = useMounted();
  const text = mounted ? new Date(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";
  return <time dateTime={iso}>{text || " "}</time>;
}

function ScoreChart({ rows }: { rows: QuizRow[] }) {
  const byTopic = new Map<string, { score: number; total: number; n: number }>();
  for (const r of rows) {
    const key = r.structure || "other";
    const cur = byTopic.get(key) ?? { score: 0, total: 0, n: 0 };
    byTopic.set(key, { score: cur.score + r.score, total: cur.total + r.total, n: cur.n + 1 });
  }
  const bars = [...byTopic.entries()].map(([k, v]) => ({ label: structureLabel(k), pct: Math.round((v.score / v.total) * 100), n: v.n }));
  return (
    <figure className="rounded-2xl border border-border bg-surface p-5">
      <figcaption className="mb-5 text-sm font-medium">Average score by topic</figcaption>
      <ul className="flex flex-col gap-3">
        {bars.map((b, i) => (
          <li key={b.label} className="grid grid-cols-[6.5rem_1fr_3rem] items-center gap-3 text-sm">
            <span className="truncate text-muted">{b.label}</span>
            <div className="h-3 overflow-hidden rounded-full bg-background" role="img" aria-label={`${b.label}: ${b.pct}% over ${b.n} quiz${b.n === 1 ? "" : "zes"}`}>
              <motion.div className="h-full rounded-full bg-accent" initial={{ width: 0 }} animate={{ width: `${b.pct}%` }}
                transition={{ duration: 0.8, delay: i * 0.08, ease: [0.22, 1, 0.36, 1] }} />
            </div>
            <span className="text-right font-mono tabular-nums">{b.pct}%</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

export function QuizHistory({ rows }: { rows: QuizRow[] }) {
  return (
    <section aria-labelledby="quiz-history-title" className="flex flex-col gap-5">
      <h2 id="quiz-history-title" className="text-2xl font-semibold">Quiz history</h2>
      {rows.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-border px-6 py-10 text-center text-muted">
          Finish a quiz at the end of a lesson and your scores will appear here.
        </p>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[1fr_1.3fr]">
          <ScoreChart rows={rows} />
          <div className="overflow-x-auto rounded-2xl border border-border bg-surface">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Your most recent quiz results</caption>
              <thead className="border-b border-border text-muted">
                <tr><th scope="col" className="px-4 py-3 font-medium">Topic</th><th scope="col" className="px-4 py-3 font-medium">Score</th><th scope="col" className="px-4 py-3 font-medium">When</th></tr>
              </thead>
              <tbody>
                {rows.slice(0, 10).map((r) => (
                  <tr key={r.id} className="border-b border-border/60 last:border-0">
                    <td className="px-4 py-3">
                      <span className="block max-w-[16rem] truncate">{r.topic}</span>
                      <span className="text-xs text-muted">{structureLabel(r.structure)}</span>
                    </td>
                    <td className="px-4 py-3 font-mono tabular-nums">
                      <span className={r.score === r.total ? "text-accent2" : ""}>{r.score}/{r.total}</span>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-muted"><LocalDate iso={r.createdAt} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
