"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { Check, X } from "lucide-react";
import type { QuizQuestion } from "@/lib/types";
import { cn } from "@/lib/utils";

function Question({ q, n, onAnswer }: { q: QuizQuestion; n: number; onAnswer: (correct: boolean) => void }) {
  const [picked, setPicked] = useState<number | null>(null);
  const answered = picked !== null;
  const correct = picked === q.answer_index;
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 text-sm font-medium text-text">
        <span className="mr-1.5 text-accent">Q{n}.</span>{q.question}
      </legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {q.options.map((opt, i) => {
          const isAnswer = i === q.answer_index;
          return (
            <button key={opt} type="button" disabled={answered} onClick={() => { setPicked(i); onAnswer(i === q.answer_index); }} aria-pressed={picked === i}
              className={cn(
                "flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-colors",
                !answered && "border-border hover:border-accent2",
                answered && isAnswer && "border-accent2 bg-accent2/15 text-text",
                answered && picked === i && !isAnswer && "border-destructive bg-destructive/10",
                answered && picked !== i && !isAnswer && "border-border text-muted",
              )}>
              <span>{opt}</span>
              {answered && isAnswer && <Check className="size-4 shrink-0 text-accent2" aria-label="correct answer" />}
              {answered && picked === i && !isAnswer && <X className="size-4 shrink-0 text-destructive" aria-label="your answer" />}
            </button>
          );
        })}
      </div>
      {answered && (
        <motion.p initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} role="status" className="text-sm text-muted">
          <span className={cn("font-semibold", correct ? "text-accent2" : "text-destructive")}>{correct ? "Correct. " : "Not quite. "}</span>
          {q.explanation}
        </motion.p>
      )}
    </fieldset>
  );
}

/**
 * `onComplete` fires once, when every question has been answered (the "submit" of this quiz).
 * `status` lets the parent report whether the result was saved.
 */
export function Quiz({ questions, lessonKey, onComplete, status }: {
  questions: QuizQuestion[];
  lessonKey: string;
  onComplete?: (score: number, total: number) => void;
  status?: React.ReactNode;
}) {
  const [answers, setAnswers] = useState<Record<string, boolean>>({});
  const [doneFor, setDoneFor] = useState<string | null>(null);
  const done = doneFor === lessonKey;
  const mine = Object.entries(answers).filter(([k]) => k.startsWith(`${lessonKey}-`));
  const score = mine.filter(([, ok]) => ok).length;

  function answer(i: number, correct: boolean) {
    const next = { ...answers, [`${lessonKey}-${i}`]: correct };
    setAnswers(next);
    const answered = Object.entries(next).filter(([k]) => k.startsWith(`${lessonKey}-`));
    if (!done && answered.length === questions.length) {
      setDoneFor(lessonKey);
      onComplete?.(answered.filter(([, ok]) => ok).length, questions.length);
    }
  }

  return (
    <section aria-labelledby="quiz-title" className="rounded-2xl border border-border bg-surface p-5">
      <h2 id="quiz-title" className="mb-1 text-lg font-semibold">Quick quiz</h2>
      <p className="mb-4 text-xs text-muted">Answers are computed by running the real data structure.</p>
      <div className="flex flex-col gap-6">
        {questions.map((q, i) => <Question key={`${lessonKey}-${i}`} q={q} n={i + 1} onAnswer={(ok) => answer(i, ok)} />)}
      </div>
      {done && (
        <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} role="status"
          className="mt-6 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-background px-4 py-3 text-sm">
          <span>You scored <span className="font-semibold text-accent">{score}</span> of {questions.length}.</span>
          {status}
        </motion.div>
      )}
    </section>
  );
}
