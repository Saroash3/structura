"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

const ACCENT = "#FF7A1A", ACCENT2 = "#4CC9F0", BORDER = "#404040", SURFACE = "#1E1E1E", TEXT = "#F2F2F2";
const spring = { type: "spring" as const, stiffness: 360, damping: 28 };

/** Counts up every `ms` while active; resets to 0 when inactive. Frozen when reduced motion is on. */
function useTicker(active: boolean, ms: number): number {
  const reduce = useReducedMotion();
  const [n, setN] = useState(0);
  const running = active && !reduce;
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setN((c) => c + 1), ms);
    return () => {
      clearInterval(t);
      setN(0);
    };
  }, [running, ms]);
  return n;
}

function Box({ value, className, pulse }: { value: number; className?: string; pulse?: boolean }) {
  return (
    <motion.div animate={pulse ? { boxShadow: ["0 0 0 0 rgba(255,122,26,0.7)", "0 0 0 10px rgba(255,122,26,0)"] } : { boxShadow: "0 0 0 0 rgba(0,0,0,0)" }}
      transition={{ duration: 0.9, repeat: pulse ? Infinity : 0 }}
      className={cn("grid size-11 place-items-center rounded-xl border-2 border-border bg-surface font-heading text-base font-semibold", className)}>
      {value}
    </motion.div>
  );
}

/* ---------------------------------------------------------------- linked list: a pointer walks the chain */
export function LinkedListMini({ active }: { active: boolean }) {
  const values = [4, 7, 2];
  const t = useTicker(active, 650);
  const at = active ? t % (values.length + 1) : -1; // last tick = "null"
  return (
    <div className="flex items-center gap-1.5">
      {values.map((v, i) => (
        <div key={v} className="flex items-center gap-1.5">
          <div className="relative">
            <Box value={v} className={cn(i === at && "border-accent", i < at && "border-accent2/70")} pulse={i === at} />
            {i === at && <motion.span layoutId="ll-ptr" transition={spring} className="absolute -top-5 left-1/2 -translate-x-1/2 text-[10px] font-semibold tracking-wider text-accent">CUR</motion.span>}
          </div>
          <span className={cn("text-sm transition-colors", i < at ? "text-accent2" : "text-muted")} aria-hidden>&rarr;</span>
        </div>
      ))}
      <span className={cn("font-mono text-xs transition-colors", at === values.length ? "text-accent" : "text-muted")}>null</span>
    </div>
  );
}

/* ---------------------------------------------------------------- stack: push, push, pop, pop */
const STACK_SCRIPT: number[][] = [[3, 8], [3, 8, 6], [3, 8, 6, 1], [3, 8, 6], [3, 8]];
export function StackMini({ active }: { active: boolean }) {
  const t = useTicker(active, 800);
  const items = STACK_SCRIPT[active ? t % STACK_SCRIPT.length : 0];
  return (
    <div className="flex h-[11.5rem] flex-col-reverse items-center justify-start gap-1.5 border-b-2 border-border px-6 pb-1.5">
      <AnimatePresence mode="popLayout" initial={false}>
        {items.map((v, i) => (
          <motion.div key={v} layout initial={{ opacity: 0, y: -40 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -40 }} transition={spring}
            className={cn("grid h-8 w-24 place-items-center rounded-lg border-2 bg-surface font-heading text-sm font-semibold",
              i === items.length - 1 ? "border-accent" : "border-border")}>
            {v}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

/* ---------------------------------------------------------------- queue: enqueue at the back, dequeue the front */
const QUEUE_SCRIPT: number[][] = [[5, 8, 3], [5, 8, 3, 9], [8, 3, 9], [8, 3, 9, 4], [3, 9, 4], [3, 9, 4, 5], [9, 4, 5], [9, 4, 5, 8], [4, 5, 8], [4, 5, 8, 3], [5, 8, 3]];
export function QueueMini({ active }: { active: boolean }) {
  const t = useTicker(active, 750);
  const items = QUEUE_SCRIPT[active ? t % QUEUE_SCRIPT.length : 0];
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-semibold tracking-wider text-accent">OUT</span>
      <div className="flex gap-2">
        <AnimatePresence mode="popLayout" initial={false}>
          {items.map((v, i) => (
            <motion.div key={v} layout initial={{ opacity: 0, x: 40 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -40 }} transition={spring}>
              <Box value={v} className={cn(i === 0 && "border-accent", i === items.length - 1 && "border-accent2")} />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
      <span className="text-[10px] font-semibold tracking-wider text-accent2">IN</span>
    </div>
  );
}

/* ---------------------------------------------------------------- BST: search for 6 lights the path 8 -> 3 -> 6 */
const TREE = [
  { v: 8, x: 100, y: 22 }, { v: 3, x: 52, y: 70 }, { v: 12, x: 148, y: 70 },
  { v: 1, x: 26, y: 118 }, { v: 6, x: 78, y: 118 }, { v: 10, x: 124, y: 118 }, { v: 14, x: 172, y: 118 },
];
const TREE_EDGES = [[0, 1], [0, 2], [1, 3], [1, 4], [2, 5], [2, 6]];
const SEARCH_PATH = [8, 3, 6];
export function TreeMini({ active }: { active: boolean }) {
  const t = useTicker(active, 600);
  const depth = active ? t % (SEARCH_PATH.length + 2) : -1; // two extra ticks to hold the found state
  const lit = new Set(SEARCH_PATH.slice(0, Math.min(depth + 1, SEARCH_PATH.length)));
  return (
    <svg viewBox="0 0 200 140" className="h-36 w-auto" aria-hidden>
      {TREE_EDGES.map(([a, b]) => {
        const on = lit.has(TREE[a].v) && lit.has(TREE[b].v);
        return <line key={`${a}-${b}`} x1={TREE[a].x} y1={TREE[a].y} x2={TREE[b].x} y2={TREE[b].y} stroke={on ? ACCENT2 : BORDER} strokeWidth={on ? 3 : 2} style={{ transition: "stroke 0.25s" }} />;
      })}
      {TREE.map((n) => {
        const found = n.v === 6 && depth >= SEARCH_PATH.length - 1;
        return (
          <g key={n.v}>
            <circle cx={n.x} cy={n.y} r="14" fill={found ? ACCENT : SURFACE} stroke={lit.has(n.v) ? ACCENT2 : BORDER} strokeWidth="2" style={{ transition: "fill 0.25s, stroke 0.25s" }} />
            <text x={n.x} y={n.y} dy="0.35em" textAnchor="middle" fontSize="11" fontWeight="600" fill={found ? "#000" : TEXT}>{n.v}</text>
          </g>
        );
      })}
    </svg>
  );
}

/* ---------------------------------------------------------------- BFS: levels glow outward from the start node */
const G_NODES = [
  { v: 1, x: 40, y: 70, level: 0 }, { v: 2, x: 100, y: 28, level: 1 }, { v: 3, x: 100, y: 112, level: 1 },
  { v: 4, x: 165, y: 28, level: 2 }, { v: 5, x: 165, y: 112, level: 2 }, { v: 6, x: 225, y: 70, level: 3 },
];
const G_EDGES = [[1, 2], [1, 3], [2, 4], [3, 5], [2, 3], [4, 6], [5, 6]];
export function BfsMini({ active }: { active: boolean }) {
  const t = useTicker(active, 700);
  const level = active ? t % 5 : -1;
  const pos = (v: number) => G_NODES.find((n) => n.v === v)!;
  return (
    <svg viewBox="0 0 265 140" className="h-36 w-auto" aria-hidden>
      {G_EDGES.map(([a, b]) => {
        const on = pos(a).level < level + 1 && pos(b).level <= level && pos(a).level !== pos(b).level;
        return <line key={`${a}-${b}`} x1={pos(a).x} y1={pos(a).y} x2={pos(b).x} y2={pos(b).y} stroke={on ? ACCENT2 : BORDER} strokeWidth={on ? 3 : 2} style={{ transition: "stroke 0.3s" }} />;
      })}
      {G_NODES.map((n) => {
        const current = n.level === level, done = n.level < level;
        return (
          <g key={n.v}>
            {current && <circle cx={n.x} cy={n.y} r="22" fill={ACCENT} opacity="0.18" />}
            <circle cx={n.x} cy={n.y} r="15" fill={current ? ACCENT : done ? BORDER : SURFACE} stroke={current ? ACCENT : done ? ACCENT2 : BORDER} strokeWidth="2" style={{ transition: "fill 0.3s, stroke 0.3s" }} />
            <text x={n.x} y={n.y} dy="0.35em" textAnchor="middle" fontSize="12" fontWeight="600" fill={current ? "#000" : TEXT}>{n.v}</text>
          </g>
        );
      })}
    </svg>
  );
}
