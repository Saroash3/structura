"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { BadgeCheck, MessageSquareCheck, Pause, Play, RotateCcw, SkipBack, SkipForward } from "lucide-react";
import { audioUrl } from "@/lib/api";
import type { Lesson, Role, State } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Stage, opCaption } from "./stage";

const ROLE_LABEL: Record<Role, string> = { setup: "setup", core: "core", edge_case: "edge case", recap: "recap" };

const SPEEDS = [0.5, 1, 1.5] as const;

function fmt(t: number) {
  const s = Math.max(0, Math.round(t));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Which true state to draw at `t` seconds into a scene's audio. */
export function frameAt(scene: Lesson["scenes"][number], t: number): State {
  // a "reset" step only clears the structure before the next kind is built: never show that empty frame
  const steps = scene.steps.filter((s) => s.last.op !== "reset");
  const n = steps.length;
  if (!n) return scene.state;
  const lead = Math.min(0.6, scene.duration * 0.1); // show the "before" state while narration starts
  if (t < lead && scene.before.kind === steps[0].kind) return scene.before;
  const i = Math.floor((Math.max(0, t - lead) / Math.max(scene.duration - lead, 0.01)) * n);
  return steps[Math.min(n - 1, i)];
}

/** play() was interrupted because new audio was loaded (switching steps, restarting): harmless, not an error. */
function isAbort(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}

export function Player({ lesson, sceneIdx, onSceneChange }: {
  lesson: Lesson;
  sceneIdx: number;
  onSceneChange: (i: number) => void;
}) {
  const audio = useRef<HTMLAudioElement>(null);
  const pendingOffset = useRef(0);
  const [playing, setPlaying] = useState(false);
  const [sceneTime, setSceneTime] = useState(0);
  const [speed, setSpeed] = useState<number>(1);
  const [audioError, setAudioError] = useState<string | null>(null);

  const scene = lesson.scenes[sceneIdx];
  const eff = useMemo(() => lesson.scenes.map((s) => s.duration / s.speed), [lesson]);
  const starts = useMemo(() => eff.map((_, i) => eff.slice(0, i).reduce((a, b) => a + b, 0)), [eff]);
  const total = eff.reduce((a, b) => a + b, 0);
  const elapsed = (starts[sceneIdx] ?? 0) + sceneTime / scene.speed;

  // Load this scene's audio whenever the scene (or its audio) changes.
  useEffect(() => {
    const el = audio.current;
    if (!el) return;
    setAudioError(null);
    el.src = audioUrl(scene.audio_url);
    el.currentTime = pendingOffset.current;
    setSceneTime(pendingOffset.current);
    pendingOffset.current = 0;
    el.playbackRate = speed * scene.speed;
    if (playing) el.play().catch((e: unknown) => { if (!isAbort(e)) setPlaying(false); });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scene.audio_url, sceneIdx, lesson]);

  useEffect(() => {
    if (audio.current) audio.current.playbackRate = speed * scene.speed;
  }, [speed, scene.speed]);

  // Smooth clock while playing.
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = () => {
      if (audio.current) setSceneTime(audio.current.currentTime);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing]);

  const toggle = useCallback(() => {
    const el = audio.current;
    if (!el) return;
    if (playing) {
      el.pause();
      setPlaying(false);
    } else {
      setAudioError(null);
      if (sceneIdx === lesson.scenes.length - 1 && el.ended && lesson.scenes.length > 1) {
        setPlaying(true); // replay from the start: step 1's audio starts itself once it is loaded
        onSceneChange(0);
        return;
      }
      if (el.ended) el.currentTime = 0;
      el.play().then(() => setPlaying(true)).catch((e: unknown) => {
        if (isAbort(e)) return; // a new step's audio replaced this one; that is not an error
        setPlaying(false);
        setAudioError(e instanceof DOMException && e.name === "NotAllowedError"
          ? "Press play again to start the narration." : "Audio could not start. Is the backend running?");
      });
    }
  }, [playing, sceneIdx, lesson.scenes.length, onSceneChange]);

  const onEnded = () => {
    if (sceneIdx < lesson.scenes.length - 1) onSceneChange(sceneIdx + 1);
    else setPlaying(false);
  };

  const seek = (t: number) => {
    let i = starts.findLastIndex((st) => st <= t);
    if (i < 0) i = 0;
    const offset = Math.max(0, (t - starts[i]) * lesson.scenes[i].speed);
    if (i === sceneIdx && audio.current) {
      audio.current.currentTime = offset;
      setSceneTime(offset);
    } else {
      pendingOffset.current = offset;
      onSceneChange(i);
    }
  };

  const frame = frameAt(scene, sceneTime);
  const caption = scene.steps.length && frame !== scene.before ? opCaption(frame) : scene.ops.length ? "" : sceneIdx === 0 ? "intro" : "concept";
  const role = scene.role ? ROLE_LABEL[scene.role] : null;

  return (
    <section aria-label="Lesson player" className="overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_0_80px_-30px_rgba(255,122,26,0.25)]">
      {/* stage */}
      <div className="relative bg-stage">
        <div className="flex items-center justify-between gap-2 px-4 pt-3 text-xs sm:text-sm">
          <span className="text-muted">
            Step{" "}
            <motion.span key={scene.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}
              className="inline-block tabular-nums text-text">{scene.id}</motion.span>{" "}of {lesson.scenes.length}
            {role && <span className={cn("ml-2 rounded-full border px-2 py-0.5 text-[11px] font-medium",
              scene.role === "core" ? "border-accent/70 text-accent" : "border-border text-muted")}>{role}</span>}
            <span className="ml-2 hidden font-mono text-muted sm:inline">{caption}</span>
          </span>
          <span className="flex items-center gap-2">
            {lesson.answer_check?.passed && (
              <span className="inline-flex items-center gap-1 rounded-full border border-accent/60 px-2 py-0.5 text-accent"
                title={lesson.answer_check.requirements.length
                  ? `Covers: ${lesson.answer_check.requirements.map((r) => r.text).join("; ")}` : "Checked against the key words of your question"}>
                <MessageSquareCheck className="size-3.5" aria-hidden /> Answers your question
              </span>
            )}
            {scene.verified && (
              <span className="inline-flex items-center gap-1 rounded-full border border-accent2/60 px-2 py-0.5 text-accent2"
                title="Every number and claim in this step was checked against the real data structure">
                <BadgeCheck className="size-3.5" aria-hidden /> Verified
              </span>
            )}
          </span>
        </div>
        <div className="flex min-h-72 items-center justify-center overflow-x-auto px-4 py-6 sm:min-h-80" aria-live="off">
          {/* layoutRoot: page reflows (e.g. after a revision) must not trigger stage layout animations */}
          <motion.div layoutRoot className="flex w-full justify-center">
            <Stage state={frame} named={scene.named} showWork={lesson.analysis?.intent === "complexity" || lesson.analysis?.intent === "question"} />
          </motion.div>
        </div>
        {/* one caption (the narration), with the running analogy as a small tag */}
        <div className="min-h-20 border-t border-border/60 px-4 py-4">
          {scene.analogy && (
            <span className="mb-2 inline-block rounded-full border border-border px-2 py-0.5 text-xs text-muted">{scene.analogy}</span>
          )}
          <AnimatePresence mode="wait">
            <motion.p key={`${lesson.topic}-${scene.id}-${scene.narration}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.25 }} className="text-base leading-relaxed text-text sm:text-lg">
              {scene.narration}
            </motion.p>
          </AnimatePresence>
        </div>
      </div>

      {/* controls */}
      <div className="flex flex-col gap-3 border-t border-border px-4 py-3">
        <label className="sr-only" htmlFor="seek">Seek</label>
        <div className="relative h-2">
          <div className="absolute inset-0 rounded-full bg-border" />
          <div className="absolute inset-y-0 left-0 rounded-full bg-accent" style={{ width: `${total ? (elapsed / total) * 100 : 0}%` }} />
          {starts.slice(1).map((st, i) => (
            <div key={i} className="absolute inset-y-0 w-0.5 bg-stage" style={{ left: `${(st / total) * 100}%` }} aria-hidden />
          ))}
          <input id="seek" type="range" min={0} max={total} step={0.1} value={Math.min(elapsed, total)}
            onChange={(e) => seek(Number(e.target.value))}
            aria-valuetext={`${fmt(elapsed)} of ${fmt(total)}`}
            className="absolute inset-0 h-2 w-full cursor-pointer opacity-0" />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => onSceneChange(Math.max(0, sceneIdx - 1))} aria-label="Previous step"
            className="grid size-9 place-items-center rounded-lg text-muted hover:text-text">
            <SkipBack className="size-4" />
          </button>
          <button type="button" onClick={toggle} aria-label={playing ? "Pause" : "Play"}
            className="grid size-10 place-items-center rounded-full bg-accent text-on-accent hover:bg-accent/90">
            {playing ? <Pause className="size-5" /> : <Play className="size-5 translate-x-px" />}
          </button>
          <button type="button" onClick={() => onSceneChange(Math.min(lesson.scenes.length - 1, sceneIdx + 1))} aria-label="Next step"
            className="grid size-9 place-items-center rounded-lg text-muted hover:text-text">
            <SkipForward className="size-4" />
          </button>
          <button type="button" onClick={() => seek(0)} aria-label="Restart"
            className="grid size-9 place-items-center rounded-lg text-muted hover:text-text">
            <RotateCcw className="size-4" />
          </button>
          <span className="ml-1 font-mono text-sm tabular-nums text-muted">
            <span className="text-text">{fmt(elapsed)}</span> / {fmt(total)}
          </span>
          <div role="group" aria-label="Playback speed" className="ml-auto flex rounded-lg border border-border p-0.5">
            {SPEEDS.map((s) => (
              <button key={s} type="button" aria-pressed={speed === s} onClick={() => setSpeed(s)}
                className={cn("rounded-md px-2.5 py-1 text-sm", speed === s ? "bg-accent2 text-on-accent" : "text-muted hover:text-text")}>
                {s}x
              </button>
            ))}
          </div>
        </div>
        {audioError && <p role="alert" className="text-sm text-destructive">{audioError}</p>}
      </div>
      <audio ref={audio} onEnded={onEnded} preload="auto"
        onError={() => setAudioError("Could not load narration audio from the backend.")} />
    </section>
  );
}
