"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AlertCircle, Check, Cpu, Loader2, Mic, RotateCw, ShieldCheck, Sparkles, Wand2 } from "lucide-react";
import { AppNav } from "@/components/app-nav";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Player } from "@/components/player";
import { Quiz } from "@/components/quiz";
import { SceneList } from "@/components/scene-list";
import { VideoExport } from "@/components/video-export";
import { ApiError, RETRYABLE, createLesson, friendlyError, reviseLesson } from "@/lib/api";
import { saveLesson, saveQuizResult, updateSavedLesson } from "@/lib/account-api";
import Link from "next/link";
import type { Lesson } from "@/lib/types";
import { cn } from "@/lib/utils";

const CHIPS = [
  { label: "Array", topic: "how does an array insert and delete" },
  { label: "Linked list", topic: "how does a linked list insert and delete" },
  { label: "Stack", topic: "how does a stack work" },
  { label: "Queue", topic: "how does a queue work" },
  { label: "Binary tree", topic: "how does a binary search tree insert and search" },
  { label: "BFS", topic: "show breadth first search on a graph" },
  { label: "Bubble sort", topic: "show bubble sort step by step" },
];

function SaveBadge({ state, onRetry }: { state: SaveState; onRetry: () => void }) {
  if (state.kind === "saving") return <span className="inline-flex items-center gap-1.5"><Loader2 className="size-3.5 animate-spin" aria-hidden />Saving</span>;
  if (state.kind === "saved") return <Link href="/dashboard" className="inline-flex items-center gap-1.5 text-accent2 hover:underline"><Check className="size-3.5" aria-hidden />Saved to your dashboard</Link>;
  if (state.kind === "error")
    return (
      <span role="alert" className="inline-flex items-center gap-1.5 text-destructive">
        Not saved: {state.message}
        <button type="button" onClick={onRetry} className="font-medium text-text underline underline-offset-2">Retry</button>
      </span>
    );
  return null;
}

function QuizSaveNote({ state }: { state: SaveState }) {
  if (state.kind === "saving") return <span className="text-muted">Saving result...</span>;
  if (state.kind === "saved") return <Link href="/dashboard" className="text-accent2 hover:underline">Saved to your quiz history</Link>;
  if (state.kind === "error") return <span className="text-destructive">Result not saved: {state.message}</span>;
  return null;
}

const STAGES = ["Planning operations", "Verifying narration", "Narrating with Piper"];

/**
 * Loading state while a lesson is generated. The request is a single call, so the stage list
 * cycles as a visual cue of the pipeline rather than reporting exact progress.
 */
function PlayerSkeleton() {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setStage((n) => (n + 1) % STAGES.length), 2200);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-surface">
      <div className="relative flex min-h-[26rem] flex-col items-center justify-center gap-8 overflow-hidden bg-stage">
        <div className="shimmer absolute inset-0" aria-hidden />
        <div className="flex gap-3" aria-hidden>
          {[0, 1, 2, 3].map((i) => <div key={i} className="size-14 animate-pulse rounded-2xl border border-border bg-surface" style={{ animationDelay: `${i * 140}ms` }} />)}
        </div>
        <ol className="relative flex flex-wrap items-center justify-center gap-2 px-4 text-xs sm:text-sm">
          {STAGES.map((label, i) => (
            <li key={label} className={cn("inline-flex items-center gap-2 rounded-full border px-3 py-1.5 transition-colors duration-500",
              i === stage ? "border-accent/70 bg-accent/10 text-text" : "border-border text-muted")}>
              <span className={cn("size-1.5 rounded-full", i === stage ? "animate-pulse bg-accent" : "bg-border")} aria-hidden />
              {label}
            </li>
          ))}
        </ol>
      </div>
      <div className="flex items-center gap-3 border-t border-border px-4 py-4" aria-hidden>
        <div className="size-10 animate-pulse rounded-full bg-border" />
        <div className="h-2 flex-1 animate-pulse rounded-full bg-border" />
      </div>
    </div>
  );
}

function EmptyPlayer() {
  return (
    <div className="flex min-h-[26rem] flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-border bg-stage p-8 text-center">
      <Sparkles className="size-6 text-accent" aria-hidden />
      <p className="font-heading text-lg">Your lesson will play here</p>
      <p className="max-w-sm text-sm text-muted">Type a topic or pick one of the chips. Every frame is computed by a real data structure, and every narrated fact is checked.</p>
    </div>
  );
}

type Level = "beginner" | "intermediate";
type SaveState = { kind: "idle" | "saving" | "saved" } | { kind: "error"; message: string };

export function Generator({ initialLevel = "beginner" }: { initialLevel?: Level }) {
  const initialTopic = (useSearchParams().get("topic") ?? "").slice(0, 200); // e.g. /app?topic=queue from the landing page
  const [topic, setTopic] = useState(initialTopic);
  const [level, setLevel] = useState<Level>(initialLevel);
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [sceneIdx, setSceneIdx] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ message: string; retryable: boolean; topic: string } | null>(null);
  const [busyNote, setBusyNote] = useState<string | null>(null); // "The AI is busy, retrying (attempt 2 of 3)..."
  const [slow, setSlow] = useState(false); // the server is quietly retrying overloaded models

  // A single request can take a while when the backend is retrying busy models: say so after 15 s.
  useEffect(() => {
    if (!loading) return;
    const t = setTimeout(() => setSlow(true), 15_000);
    return () => { clearTimeout(t); setSlow(false); };
  }, [loading]);
  const [instruction, setInstruction] = useState("");
  const [revising, setRevising] = useState(false);
  const [reviseMsg, setReviseMsg] = useState<{ ok: boolean; text: string; before?: string; after?: string } | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [save, setSave] = useState<SaveState>({ kind: "idle" });
  const [quizSave, setQuizSave] = useState<SaveState>({ kind: "idle" });
  const [gen, setGen] = useState(0); // bumps per generated lesson so the quiz resets

  /** Auto-save: create the lesson on first save, replace its content after revisions. */
  async function persist(l: Lesson, id: string | null) {
    setSave({ kind: "saving" });
    try {
      if (id) await updateSavedLesson(id, l);
      else setSavedId((await saveLesson(l)).id);
      setSave({ kind: "saved" });
    } catch (e) {
      setSave({ kind: "error", message: e instanceof Error ? e.message : "Could not save." });
    }
  }

  async function onQuizComplete(score: number, total: number) {
    if (!lesson) return;
    setQuizSave({ kind: "saving" });
    try {
      await saveQuizResult({ lessonId: savedId, topic: lesson.plan.topic, structure: lesson.structure, score, total });
      setQuizSave({ kind: "saved" });
    } catch (e) {
      setQuizSave({ kind: "error", message: e instanceof Error ? e.message : "Could not save." });
    }
  }

  async function generate(t: string) {
    const q = t.trim();
    if (q.length < 2 || loading) return;
    setTopic(q);
    setLoading(true);
    setError(null);
    setBusyNote(null);
    setReviseMsg(null);
    try {
      const l = { ...(await createLessonPolitely(q, level)), level };
      setLesson(l);
      setSceneIdx(0);
      setGen((g) => g + 1);
      setSavedId(null);
      setQuizSave({ kind: "idle" });
      void persist(l, null);
    } catch (e) {
      const { code, message } = friendlyError(e);
      setError({ message, retryable: RETRYABLE.has(code), topic: q });
    } finally {
      setLoading(false);
      setBusyNote(null);
    }
  }

  /** The backend already retries busy models; if it still says "busy", wait and ask again (3 attempts in all). */
  async function createLessonPolitely(q: string, lv: Level): Promise<Lesson> {
    const attempts = 3;
    for (let attempt = 1; ; attempt++) {
      try {
        return await createLesson(q, lv);
      } catch (e) {
        if (!(e instanceof ApiError) || e.code !== "ai_busy" || attempt >= attempts) throw e;
        setBusyNote(`The AI is busy, retrying (attempt ${attempt + 1} of ${attempts})...`);
        await new Promise((r) => setTimeout(r, 4000 * attempt));
      }
    }
  }

  async function revise(e: React.FormEvent) {
    e.preventDefault();
    if (!lesson || instruction.trim().length < 2) return;
    setRevising(true);
    setReviseMsg(null);
    try {
      const updated = await reviseLesson(lesson.plan, lesson.scenes[sceneIdx]?.id ?? null, instruction.trim(), lesson.scenes);
      const rev = updated.revised;
      const id = rev?.scene_id ?? 1;
      if (rev?.change === "none") {
        // nothing changed: keep the lesson as it is and say so honestly
        setSceneIdx(id - 1);
        setReviseMsg({ ok: false, text: rev.message ?? "I couldn't change this step, try describing what confused you." });
        return;
      }
      const next = { ...updated, quiz: lesson.quiz, level: lesson.level };
      setLesson(next);
      void persist(next, savedId); // revised versions replace the saved lesson's content
      setSceneIdx(id - 1);
      setReviseMsg(rev?.change === "speed"
        ? { ok: true, text: `Step ${id} speed changed. Other steps unchanged.` }
        : { ok: true, text: `Step ${id} rewritten and re-verified. Other steps unchanged.`, before: rev?.before, after: rev?.after });
      setInstruction("");
    } catch (err) {
      setReviseMsg({ ok: false, text: friendlyError(err).message });
    } finally {
      setRevising(false);
    }
  }

  return (
    <>
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-10 focus:rounded-lg focus:bg-accent focus:px-3 focus:py-2 focus:text-on-accent">
        Skip to content
      </a>
      <AppNav current="app" />
      <main id="main" className="container-page grid gap-10 py-10 lg:grid-cols-[minmax(0,20rem)_minmax(0,1fr)] lg:gap-12 lg:py-14">
        {/* left column */}
        <div id="lessons" className="flex flex-col gap-6">
          <div>
            <h1 className="text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
              Watch data structures move, step by step.
            </h1>
            <p className="mt-3 text-muted">Ask about a structure. Get an animated, narrated lesson where every step is run on real code and every sentence is fact-checked.</p>
          </div>

          <form onSubmit={(e) => { e.preventDefault(); generate(topic); }} className="flex flex-col gap-3">
            <label htmlFor="topic" className="text-sm font-medium">Topic</label>
            <div className="flex gap-2">
              <Input id="topic" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="how does a queue work"
                className="h-11 flex-1 bg-surface text-base" autoComplete="off" />
              <Button type="submit" disabled={loading || topic.trim().length < 2} className="h-11 px-4 font-semibold">
                {loading ? <Loader2 className="animate-spin" aria-hidden /> : <Wand2 aria-hidden />}
                Generate
              </Button>
            </div>
            <div role="radiogroup" aria-label="Level" className="flex gap-1 self-start rounded-lg border border-border p-0.5 text-sm">
              {(["beginner", "intermediate"] as const).map((lv) => (
                <button key={lv} type="button" role="radio" aria-checked={level === lv} onClick={() => setLevel(lv)}
                  className={cn("rounded-md px-3 py-1 capitalize", level === lv ? "bg-surface text-text" : "text-muted hover:text-text")}>
                  {lv}
                </button>
              ))}
            </div>
          </form>

          <div>
            <h2 className="mb-2 text-sm font-medium text-muted">Try a topic</h2>
            <ul className="flex flex-wrap gap-2">
              {CHIPS.map((c) => (
                <li key={c.label}>
                  <button type="button" onClick={() => generate(c.topic)} disabled={loading}
                    className="rounded-full border border-border bg-surface px-3 py-1.5 text-sm hover:border-accent2 hover:text-accent2 disabled:opacity-50">
                    {c.label}
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <form onSubmit={revise} className="flex flex-col gap-2 rounded-2xl border border-border bg-surface p-5">
            <label htmlFor="revise" className="font-heading font-semibold">Revise the video</label>
            <p className="text-xs text-muted">Changes one step only. Name it (&quot;step 4&quot;) or it applies to the current step.</p>
            <div className="flex gap-2">
              <Input id="revise" value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="slow down step 4"
                disabled={!lesson} className="h-10 flex-1 bg-background" autoComplete="off" />
              <Button type="submit" disabled={!lesson || revising || instruction.trim().length < 2} className="h-10 px-3 font-semibold">
                {revising ? <Loader2 className="animate-spin" aria-hidden /> : null}
                Revise
              </Button>
            </div>
            {!lesson && <p className="text-xs text-muted">Generate a lesson first.</p>}
            {reviseMsg && (
              <div role="status" className="flex flex-col gap-2">
                <p className={cn("text-sm", reviseMsg.ok ? "text-accent2" : "text-destructive")}>{reviseMsg.text}</p>
                {reviseMsg.before && reviseMsg.after && (
                  <dl className="grid gap-1.5 rounded-lg border border-border bg-background p-3 text-xs leading-relaxed">
                    <dt className="font-medium text-muted">Before</dt>
                    <dd className="text-muted line-through decoration-muted/60">{reviseMsg.before}</dd>
                    <dt className="mt-1 font-medium text-accent2">After</dt>
                    <dd className="text-text">{reviseMsg.after}</dd>
                  </dl>
                )}
              </div>
            )}
          </form>
        </div>

        {/* right column */}
        <div className="flex min-w-0 flex-col gap-6">
          <div aria-live="polite" className="sr-only">
            {loading ? busyNote ?? (slow ? "The AI is busy, retrying" : "Planning, verifying, narrating") : lesson ? `Lesson ready: ${lesson.topic}` : ""}
          </div>
          {error && (
            <div role="alert" className="flex flex-wrap items-start gap-3 rounded-xl border border-destructive/60 bg-destructive/10 p-4 text-sm">
              <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-text">Could not build the lesson</p>
                <p className="text-muted">{error.message}</p>
              </div>
              {error.retryable && (
                <Button type="button" onClick={() => generate(error.topic)} className="h-9 gap-1.5 px-3 font-semibold">
                  <RotateCw className="size-4" aria-hidden /> Try again
                </Button>
              )}
            </div>
          )}
          {loading ? (
            <div className="flex flex-col gap-3">
              <p className="flex items-center gap-2 text-sm text-muted">
                <Loader2 className="size-4 animate-spin text-accent" aria-hidden />
                {busyNote ?? (slow ? "The AI is busy, retrying... this can take up to a minute." : "Planning, verifying, narrating... this usually takes 10 to 20 seconds.")}
              </p>
              <PlayerSkeleton />
            </div>
          ) : lesson ? (
            <>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 className="text-2xl font-semibold">{lesson.plan.topic}</h2>
                <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
                  {lesson.structure.replace("_", " ")} &middot; {lesson.scenes.length} steps &middot; all verified
                  <SaveBadge state={save} onRetry={() => void persist(lesson, savedId)} />
                </span>
              </div>
              <Player lesson={lesson} sceneIdx={sceneIdx} onSceneChange={setSceneIdx} />
              <VideoExport lesson={lesson} lessonId={savedId} />
              <div className="grid gap-6 xl:grid-cols-2">
                <SceneList scenes={lesson.scenes} active={sceneIdx} onSelect={setSceneIdx} revisedId={lesson.revised?.scene_id} />
                {lesson.quiz && <Quiz questions={lesson.quiz} lessonKey={`gen-${gen}`} onComplete={onQuizComplete} status={<QuizSaveNote state={quizSave} />} />}
              </div>
            </>
          ) : (
            <EmptyPlayer />
          )}
        </div>
      </main>

      <section id="how" aria-labelledby="how-title" className="border-t border-border">
        <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
          <h2 id="how-title" className="mb-6 text-xl font-semibold">How it works</h2>
          <ol className="grid gap-4 md:grid-cols-3">
            {[
              { icon: Sparkles, title: "1. Plan", text: "Gemini writes a scene plan made only of operations, like enqueue(5). It never draws a state." },
              { icon: ShieldCheck, title: "2. Run and verify", text: "Python runs every operation on a real data structure. Each sentence of narration is checked against the true state, and fixed if it is wrong." },
              { icon: Mic, title: "3. Narrate locally", text: "Piper turns each scene into speech on this machine. Each animation lasts exactly as long as its audio." },
            ].map(({ icon: Icon, title, text }) => (
              <li key={title} className="rounded-xl border border-border bg-surface p-4">
                <Icon className="mb-3 size-5 text-accent" aria-hidden />
                <h3 className="mb-1 font-semibold">{title}</h3>
                <p className="text-sm text-muted">{text}</p>
              </li>
            ))}
          </ol>
          <p className="mt-6 flex items-center gap-2 text-xs text-muted"><Cpu className="size-3.5" aria-hidden /> Everything except the Gemini call runs locally.</p>
        </div>
      </section>
    </>
  );
}
