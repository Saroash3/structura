"use client";

import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AnimatePresence, MotionGlobalConfig, motion } from "motion/react";
import { CheckCircle2 } from "lucide-react";
import type { Lesson, QuizQuestion } from "@/lib/types";
import { frameAt } from "./player";
import { Stage } from "./stage";

type RenderLesson = Pick<Lesson, "topic" | "structure" | "scenes" | "analysis"> & { quiz: QuizQuestion[]; quiz_seconds: number; total: number };
/** A moment where the picture changes: `at` is the time in the video (seconds); `motion` = something animates there. */
type Keyframe = { at: number; scene: number; motion: boolean };

declare global {
  interface Window {
    __renderReady?: boolean;
    __renderError?: string;
    __renderPlan?: () => { total: number; keyframes: Keyframe[] };
    __renderGoto?: (at: number, animate: boolean) => Promise<void>;
  }
}

function startsOf(scenes: Lesson["scenes"]) {
  const out: number[] = [];
  let acc = 0;
  for (const s of scenes) {
    out.push(acc);
    acc += s.duration / (s.speed || 1);
  }
  return out;
}

/** Every moment the frame changes, with the same timing rule as the player's frameAt (lead, then the steps evenly). */
function keyframesOf(l: RenderLesson): Keyframe[] {
  const starts = startsOf(l.scenes);
  const out: Keyframe[] = [];
  l.scenes.forEach((s, i) => {
    const speed = s.speed || 1;
    out.push({ at: starts[i], scene: i, motion: true }); // new caption, maybe a new structure
    const n = s.steps.filter((st) => st.last.op !== "reset").length;
    if (!n) return;
    const lead = Math.min(0.6, s.duration * 0.1);
    for (let k = 0; k < n; k++) {
      const t = lead + (k * (s.duration - lead)) / n; // audio time where step k starts
      out.push({ at: starts[i] + t / speed, scene: i, motion: true });
    }
  });
  if (l.quiz.length) out.push({ at: l.total - l.quiz_seconds, scene: -1, motion: true });
  const dedup: Keyframe[] = [];
  for (const k of out.sort((a, b) => a.at - b.at)) {
    if (!dedup.length || k.at - dedup[dedup.length - 1].at > 0.02) dedup.push(k);
  }
  return dedup;
}

const twoFrames = () => new Promise<void>((r) => requestAnimationFrame(() => requestAnimationFrame(() => r())));

/**
 * The video frame (1280x720) the backend captures with headless Chromium. It is a pure function of the video time:
 * the backend asks for the keyframes (every moment the picture changes) and jumps to each one with __renderGoto,
 * capturing a single frame for a still and ~12 fps only while something animates (see backend/video.py).
 */
export function RenderView() {
  const params = useSearchParams();
  const job = params.get("job") ?? "";
  const api = params.get("api") ?? "http://localhost:8000";
  const [lesson, setLesson] = useState<RenderLesson | null>(null);
  const [at, setAt] = useState(0);
  const lessonRef = useRef<RenderLesson | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${api}/export/${encodeURIComponent(job)}/lesson`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`lesson not found (${r.status})`))))
      .then(async (data: RenderLesson) => {
        if (cancelled) return;
        lessonRef.current = data;
        setLesson(data);
        await document.fonts.ready;
        window.__renderPlan = () => ({ total: data.total, keyframes: keyframesOf(data) });
        window.__renderGoto = async (t: number, animate: boolean) => {
          MotionGlobalConfig.skipAnimations = !animate; // a jump (first frame of a worker's range) lands on the final layout
          setAt(t + 0.001); // just after the boundary, so the new frame is shown
          await twoFrames();
          MotionGlobalConfig.skipAnimations = false;
        };
        await twoFrames();
        window.__renderReady = true;
      })
      .catch((e: unknown) => { window.__renderError = e instanceof Error ? e.message : String(e); });
    return () => { cancelled = true; };
  }, [api, job]);

  if (!lesson) return <div className="fixed inset-0 z-[100] bg-stage" />;

  const starts = startsOf(lesson.scenes);
  const scenesEnd = lesson.total - lesson.quiz_seconds;
  const showQuiz = lesson.quiz.length > 0 && at >= scenesEnd;
  let idx = 0;
  while (idx + 1 < starts.length && starts[idx + 1] <= at) idx++;
  const scene = lesson.scenes[idx];
  const frame = frameAt(scene, Math.max(0, (Math.min(at, scenesEnd) - starts[idx]) * (scene.speed || 1)));

  return (
    <div className="fixed inset-0 z-[100] flex h-[720px] w-[1280px] flex-col overflow-hidden bg-stage text-text">
      <header className="flex items-center justify-between border-b border-border px-10 py-5">
        <div className="flex items-center gap-3">
          <span className="flex gap-1" aria-hidden>
            <span className="size-3 rounded-sm bg-accent" /><span className="size-3 rounded-sm bg-accent2" /><span className="size-3 rounded-sm bg-text" />
          </span>
          <span className="font-heading text-lg font-semibold">Structura</span>
          <span className="ml-4 max-w-[680px] truncate text-lg text-muted">{lesson.topic}</span>
        </div>
        <span className="font-mono text-base text-muted">
          {showQuiz ? "Quiz" : <>Step <span className="text-text">{scene.id}</span> of {lesson.scenes.length}</>}
        </span>
      </header>

      {showQuiz ? (
        <QuizSlide quiz={lesson.quiz} />
      ) : (
        <>
          <main className="flex min-h-0 flex-1 items-center justify-center px-10 py-6">
            <motion.div layoutRoot className="flex w-full scale-125 justify-center">
              <Stage state={frame} named={scene.named}
                showWork={lesson.analysis?.intent === "complexity" || lesson.analysis?.intent === "question"} />
            </motion.div>
          </main>
          <footer className="min-h-[150px] border-t border-border bg-surface px-10 py-5">
            {scene.analogy && (
              <span className="mb-2 inline-block rounded-full border border-border px-3 py-0.5 text-sm text-muted">{scene.analogy}</span>
            )}
            <AnimatePresence mode="wait">
              <motion.p key={scene.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }} className="text-[26px] leading-snug text-text">
                {scene.narration}
              </motion.p>
            </AnimatePresence>
          </footer>
        </>
      )}
    </div>
  );
}

/** The last slide: every quiz question with its verified answer. */
function QuizSlide({ quiz }: { quiz: QuizQuestion[] }) {
  return (
    <main className="flex flex-1 flex-col justify-center gap-6 px-16">
      <h2 className="font-heading text-4xl font-semibold">Quick quiz: the answers</h2>
      <ol className="flex flex-col gap-5">
        {quiz.map((q, i) => (
          <li key={i} className="rounded-2xl border border-border bg-surface px-6 py-4">
            <p className="text-xl text-text">{i + 1}. {q.question}</p>
            <p className="mt-2 flex items-center gap-2 text-xl font-semibold text-accent">
              <CheckCircle2 className="size-5 shrink-0" aria-hidden /> {q.options[q.answer_index]}
            </p>
          </li>
        ))}
      </ol>
    </main>
  );
}
