"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, LayoutGroup, motion, useInView, useReducedMotion } from "motion/react";
import { BadgeCheck, Pause, Play } from "lucide-react";
import { BorderBeam } from "@/components/ui/border-beam";
import { cn } from "@/lib/utils";

type Op = { kind: "enqueue"; value: number } | { kind: "dequeue" };
type Item = { id: number; value: number };
type Frame = { op: string; items: Item[]; caption: string; changed: number | null };

// The lesson the card loops: run on a real (tiny) queue so every frame is the true state.
const SCRIPT: Op[] = [
  { kind: "enqueue", value: 5 },
  { kind: "enqueue", value: 8 },
  { kind: "enqueue", value: 3 },
  { kind: "dequeue" },
];

function buildFrames(): Frame[] {
  let items: Item[] = [];
  let nextId = 0;
  const frames: Frame[] = [{ op: "new Queue()", items, caption: "An empty queue. Items join at the back and leave from the front.", changed: null }];
  for (const op of SCRIPT) {
    if (op.kind === "enqueue") {
      const id = nextId++;
      items = [...items, { id, value: op.value }];
      frames.push({
        op: `enqueue(${op.value})`,
        items,
        caption: items.length === 1
          ? `${op.value} joins the back. It is the only item, so the front is also ${op.value}.`
          : `${op.value} joins the back. The front is still ${items[0].value}, and the size is ${items.length}.`,
        changed: id,
      });
    } else {
      const [removed, ...rest] = items;
      items = rest;
      frames.push({ op: "dequeue()", items, caption: `${removed.value} leaves from the front. The new front is ${items[0]?.value}.`, changed: null });
    }
  }
  return frames;
}

export const DEMO_FRAMES = buildFrames();
const STEP_MS = 2600;
const spring = { type: "spring" as const, stiffness: 340, damping: 28 };

/** Caption that types itself out (instant when reduced motion is on). */
function TypedCaption({ text }: { text: string }) {
  const reduce = useReducedMotion();
  const [n, setN] = useState(0);
  useEffect(() => {
    if (reduce) return;
    const t = setInterval(() => setN((c) => (c >= text.length ? c : c + 1)), 18);
    return () => clearInterval(t);
  }, [text, reduce]);
  const shown = reduce ? text : text.slice(0, n);
  return (
    <p className="min-h-12 text-[15px] leading-relaxed text-text sm:text-base">
      {shown}
      {!reduce && n < text.length && <span className="ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 animate-pulse bg-accent" aria-hidden />}
    </p>
  );
}

export function LiveDemo({ onStep }: { onStep?: (step: number, total: number) => void }) {
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(true);
  const frame = DEMO_FRAMES[i];
  const total = DEMO_FRAMES.length;
  const ref = useRef<HTMLElement>(null);
  const onScreen = useInView(ref, { margin: "100px" }); // nothing loops while the card is offscreen
  const running = playing && onScreen;

  useEffect(() => {
    if (!running) return;
    const t = setTimeout(() => setI((n) => (n + 1) % total), STEP_MS);
    return () => clearTimeout(t);
  }, [i, running, total]);
  useEffect(() => onStep?.(i + 1, total), [i, total, onStep]);

  return (
    <figure ref={ref} data-offscreen={onScreen ? undefined : "true"} aria-label="Live preview: a queue lesson playing on its own"
      className="relative overflow-hidden rounded-2xl border border-border bg-surface shadow-[0_0_80px_-20px_rgba(255,122,26,0.25)]">
      {onScreen && <BorderBeam size={120} duration={9} colorFrom="#FF7A1A" colorTo="rgba(255,122,26,0.15)" borderWidth={1.5} />}
      <div className="bg-stage">
        {/* header */}
        <div className="flex items-center justify-between gap-3 border-b border-border/60 px-5 py-3">
          <div className="flex items-center gap-2.5 text-xs">
            <span className="flex gap-1" aria-hidden>
              <span className="size-2 rounded-full bg-border" /><span className="size-2 rounded-full bg-border" /><span className="size-2 rounded-full bg-border" />
            </span>
            <span className="text-muted">Step <span className="tabular-nums text-text">{i + 1}</span> of {total}</span>
          </div>
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.span key={i} initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ opacity: 0 }}
              transition={{ type: "spring", stiffness: 500, damping: 22 }}
              className="inline-flex items-center gap-1 rounded-full border border-accent2/60 bg-accent2/10 px-2.5 py-0.5 text-xs font-medium text-accent2">
              <BadgeCheck className="size-3.5" aria-hidden /> Verified
            </motion.span>
          </AnimatePresence>
        </div>

        {/* stage */}
        <div className="relative flex h-60 flex-col items-center justify-center gap-6 px-4 sm:h-72">
          <code className="rounded-md border border-border bg-surface px-2.5 py-1 font-mono text-xs text-accent">{frame.op}</code>
          <LayoutGroup>
            <ul className="flex min-h-24 items-start gap-2.5 sm:gap-4" aria-hidden>
              <AnimatePresence mode="popLayout">
                {frame.items.map((item, idx) => {
                  const front = idx === 0, back = idx === frame.items.length - 1;
                  const active = item.id === frame.changed;
                  return (
                    <motion.li key={item.id} layout initial={{ opacity: 0, x: 80, scale: 0.9 }} animate={{ opacity: 1, x: 0, scale: 1 }}
                      exit={{ opacity: 0, x: -90, scale: 0.9, transition: { duration: 0.4 } }} transition={spring}
                      className="flex flex-col items-center gap-2">
                      <motion.div
                        animate={active ? { boxShadow: ["0 0 0 0 rgba(255,122,26,0.7)", "0 0 0 14px rgba(255,122,26,0)"] } : { boxShadow: "0 0 0 0 rgba(0,0,0,0)" }}
                        transition={{ duration: 1.2, repeat: active ? Infinity : 0 }}
                        className={cn("grid size-16 place-items-center rounded-2xl border-2 bg-surface font-heading text-2xl font-semibold sm:size-20 sm:text-3xl",
                          front ? "border-accent" : back ? "border-accent2" : "border-border")}>
                        {item.value}
                      </motion.div>
                      <div className="flex h-5 gap-1">
                        {front && <motion.span layoutId="demo-front" transition={spring} className="text-[11px] font-semibold tracking-wider text-accent">FRONT</motion.span>}
                        {back && <motion.span layoutId="demo-back" transition={spring} className="text-[11px] font-semibold tracking-wider text-accent2">BACK</motion.span>}
                      </div>
                    </motion.li>
                  );
                })}
              </AnimatePresence>
              {frame.items.length === 0 && (
                <li className="rounded-2xl border border-dashed border-border px-8 py-6 text-sm text-muted">empty queue</li>
              )}
            </ul>
          </LayoutGroup>
        </div>

        {/* caption */}
        <figcaption className="border-t border-border/60 px-5 py-4">
          <TypedCaption key={i} text={frame.caption} />
        </figcaption>
      </div>

      {/* controls */}
      <div className="flex items-center gap-3 border-t border-border px-5 py-3">
        <button type="button" onClick={() => setPlaying((p) => !p)} aria-label={playing ? "Pause preview" : "Play preview"}
          className="grid size-9 shrink-0 place-items-center rounded-full bg-accent text-on-accent transition-transform hover:bg-accent/90 active:scale-90">
          {playing ? <Pause className="size-4" /> : <Play className="size-4 translate-x-px" />}
        </button>
        <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-border" aria-hidden>
          <div className="absolute inset-y-0 left-0 rounded-full bg-accent/35" style={{ width: `${(i / total) * 100}%` }} />
          <motion.div key={`${i}-${running}`} className="absolute inset-y-0 left-0 rounded-full bg-accent"
            initial={{ width: `${(i / total) * 100}%` }}
            animate={{ width: running ? `${((i + 1) / total) * 100}%` : `${(i / total) * 100}%` }}
            transition={{ duration: running ? STEP_MS / 1000 : 0, ease: "linear" }} />
        </div>
        <span className="font-mono text-xs tabular-nums text-muted">0:{String(Math.round((i * STEP_MS) / 1000)).padStart(2, "0")}</span>
      </div>
    </figure>
  );
}
