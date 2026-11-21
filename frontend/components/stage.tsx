"use client";

import { AnimatePresence, motion, type Transition } from "motion/react";
import type { ReactNode } from "react";
import type { GraphNode, Label, State, TreeNode } from "@/lib/types";
import { cn } from "@/lib/utils";

const spring: Transition = { type: "spring", stiffness: 320, damping: 28 };
const ACCENT = "#FF7A1A";
const ACCENT2 = "#4CC9F0";
const BORDER = "#404040";
const SURFACE = "#1E1E1E";
const TEXT = "#F2F2F2";
const MUTED = "#A8A8A8";

/** Stable React keys for values that may repeat: "7#0", "7#1", ... */
function keyed(items: Label[]) {
  const seen: Record<string, number> = {};
  return items.map((v) => `${v}#${(seen[v] = (seen[v] ?? -1) + 1)}`);
}

/** Pulsing accent ring around the element being changed. */
const pulse = {
  boxShadow: ["0 0 0 0 rgba(255,122,26,0.75)", "0 0 0 12px rgba(255,122,26,0)"],
  transition: { duration: 1.1, repeat: Infinity },
};

function Cell({ value, active, tone, label, labelTone }: {
  value: Label; active?: boolean; tone?: "front" | "back" | "path" | "sorted"; label?: string; labelTone?: "accent" | "accent2";
}) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <motion.div
        animate={active ? pulse : { boxShadow: "0 0 0 0 rgba(0,0,0,0)" }}
        className={cn(
          "grid size-12 place-items-center rounded-xl border bg-surface font-heading text-lg font-semibold sm:size-14",
          tone === "front" && "border-accent",
          tone === "back" && "border-accent2",
          tone === "path" && "border-accent2 bg-accent2/15",
          !tone && "border-border",
          active && "border-accent",
        )}
      >
        {value}
      </motion.div>
      <span className={cn("h-4 text-xs font-medium uppercase tracking-wide",
        labelTone === "accent" ? "text-accent" : labelTone === "accent2" ? "text-accent2" : "text-muted")}>
        {label ?? ""}
      </span>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      className="rounded-xl border border-dashed border-border px-6 py-4 text-sm text-muted">
      {text}
    </motion.div>
  );
}

// ------------------------------------------------------------------ array
function ArrayStage({ s }: { s: State }) {
  const keys = keyed(s.items);
  const op = s.last.op ?? "";
  const target = ["append", "insert_at", "set", "get", "scan"].includes(op) ? s.last.index ?? -1 : -1;
  // elements that moved because of an insert or delete
  const shiftedFrom = op === "insert_at" ? (s.last.index ?? 0) + 1 : op === "delete_at" ? s.last.index ?? 0 : Infinity;
  // linear search: every index compared with the target so far
  const scanned = new Set(op === "scan" ? s.scan?.checked ?? [] : []);
  return (
    <ul className="flex min-h-20 flex-wrap items-start justify-center gap-1.5 sm:gap-2">
      <AnimatePresence mode="popLayout">
        {s.items.map((v, i) => (
          <motion.li key={keys[i]} layout initial={{ opacity: 0, y: -50 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 50, transition: { duration: 0.35 } }} transition={spring}>
            <Cell value={v} active={i === target} tone={i >= shiftedFrom || scanned.has(i) ? "path" : undefined}
              label={op === "scan" && i === target ? (s.last.found ? "found" : `≠ ${s.last.target}`) : `[${i}]`}
              labelTone={i === target ? "accent" : i >= shiftedFrom || scanned.has(i) ? "accent2" : undefined} />
          </motion.li>
        ))}
      </AnimatePresence>
      {s.items.length === 0 && <Empty text="The array is empty" />}
    </ul>
  );
}

// ------------------------------------------------------------------ queue
const QUEUE_NOTE: Record<string, string> = {
  circular: "circular queue: the back wraps round to the front",
  priority: "priority queue: the smallest number is served first",
  deque: "deque: join and leave at both ends",
};

function QueueStage({ s }: { s: State }) {
  const keys = keyed(s.items);
  const op = s.last.op;
  const changed = op === "enqueue" ? s.last.index ?? s.items.length - 1 : op === "peek" || op === "push_front" ? 0 : -1;
  const v = s.variant ?? "simple";
  return (
    <div className="flex flex-col items-center gap-4">
      {QUEUE_NOTE[v] && <p className="text-xs uppercase tracking-wide text-accent2">{QUEUE_NOTE[v]}</p>}
      <div className="flex items-center gap-2 text-xs text-muted" aria-hidden>
        <span>{v === "deque" ? "joins / leaves" : "leaves here"}</span><span className="text-accent">{v === "deque" ? "\u2194" : "\u2190"}</span>
        <span className="mx-6 h-px w-16 bg-border" />
        <span className="text-accent2">{v === "deque" ? "\u2194" : "\u2190"}</span><span>{v === "deque" ? "joins / leaves" : "joins here"}</span>
      </div>
      <motion.ul layout className="flex min-h-20 flex-wrap items-start justify-center gap-2 sm:gap-3">
        <AnimatePresence mode="popLayout">
          {s.items.map((v, i) => (
            <motion.li key={keys[i]} layout initial={{ opacity: 0, x: 60 }} animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -70, transition: { duration: 0.35 } }} transition={spring}>
              <Cell value={v} active={i === changed}
                tone={i === 0 ? "front" : i === s.items.length - 1 ? "back" : undefined}
                label={i === 0 ? "front" : i === s.items.length - 1 ? "back" : undefined}
                labelTone={i === 0 ? "accent" : "accent2"} />
            </motion.li>
          ))}
        </AnimatePresence>
        {s.items.length === 0 && <Empty text="The queue is empty" />}
      </motion.ul>
      {v === "circular" && s.items.length > 0 && (
        <svg width="260" height="26" viewBox="0 0 260 26" aria-hidden className="-mt-2">
          <path d="M250 2 C250 24, 10 24, 10 2" fill="none" stroke={ACCENT2} strokeWidth={2} strokeDasharray="5 4" />
          <path d="M4 8 L10 1 L16 8" fill="none" stroke={ACCENT2} strokeWidth={2} />
        </svg>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ kinds of array: 2D grid, static vs dynamic, jagged
function GridStage({ s }: { s: State }) {
  const cells = s.cells ?? [];
  const hot = s.last.op === "get2" || s.last.op === "set2" ? [s.last.row ?? -1, s.last.col ?? -1] : [-1, -1];
  if (!cells.length) return <Empty text="The 2D array is empty" />;
  return (
    <div className="flex flex-col items-center gap-1.5" role="img" aria-label={`2D array, ${cells.length} rows by ${cells[0].length} columns`}>
      <div className="flex gap-1.5 pl-14 sm:gap-2">
        {cells[0].map((_, c) => (
          <span key={c} className={cn("w-12 text-center text-xs uppercase tracking-wide sm:w-14", c === hot[1] ? "text-accent" : "text-muted")}>col {c}</span>
        ))}
      </div>
      {cells.map((row, r) => (
        <div key={r} className="flex items-center gap-1.5 sm:gap-2">
          <span className={cn("w-12 whitespace-nowrap text-right text-xs uppercase tracking-wide", r === hot[0] ? "text-accent" : "text-muted")}>row {r}</span>
          {row.map((v, c) => (
            <motion.div key={`${r}-${c}`} initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} transition={spring}>
              <Cell value={v} active={r === hot[0] && c === hot[1]} tone={r === hot[0] || c === hot[1] ? "path" : undefined} />
            </motion.div>
          ))}
        </div>
      ))}
    </div>
  );
}

function DynArrayStage({ s }: { s: State }) {
  const cap = s.capacity ?? s.items.length;
  const l = s.last;
  const slots = Array.from({ length: cap }, (_, i) => (i < s.items.length ? s.items[i] : null));
  return (
    <div className="flex flex-col items-center gap-3">
      <p className="text-xs uppercase tracking-wide text-muted">
        {s.mode === "static" ? "static array: fixed size" : "dynamic array: grows when full"} · {s.items.length} of {cap} slots used
      </p>
      {l.resized && (
        <p className="text-sm text-accent2">full: moved to {l.new_capacity} slots, copied {l.copied} values</p>
      )}
      <ul className="flex flex-wrap items-start justify-center gap-1.5 sm:gap-2">
        {slots.map((v, i) => (
          <motion.li key={`${cap}-${i}`} layout initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} transition={spring}>
            {v === null ? (
              <div className="flex flex-col items-center gap-1.5">
                <div className="grid size-12 place-items-center rounded-xl border border-dashed border-border text-xs text-muted sm:size-14">free</div>
                <span className="h-4 text-xs text-muted">[{i}]</span>
              </div>
            ) : (
              <Cell value={v} active={l.op === "append" && l.index === i} tone={l.resized && i < (l.copied ?? 0) ? "path" : undefined}
                label={`[${i}]`} labelTone={l.op === "append" && l.index === i ? "accent" : undefined} />
            )}
          </motion.li>
        ))}
        {l.refused && (
          <li className="flex flex-col items-center gap-1.5">
            <div className="grid size-12 place-items-center rounded-xl border border-destructive bg-surface font-heading text-lg font-semibold text-destructive line-through sm:size-14">{l.value}</div>
            <span className="h-4 text-xs font-medium uppercase text-destructive">no room</span>
          </li>
        )}
      </ul>
    </div>
  );
}

function JaggedStage({ s }: { s: State }) {
  const cells = s.cells ?? [];
  const hot = s.last.op === "get2" ? [s.last.row ?? -1, s.last.col ?? -1] : [-1, -1];
  const added = s.last.op === "row" ? s.last.row ?? -1 : -1;
  if (!cells.length) return <Empty text="The jagged array has no rows yet" />;
  return (
    <div className="flex flex-col items-start gap-1.5" role="img" aria-label={`Jagged array with rows of length ${cells.map((r) => r.length).join(", ")}`}>
      {cells.map((row, r) => (
        <motion.div key={r} className="flex items-center gap-1.5 sm:gap-2" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={spring}>
          <span className={cn("w-12 whitespace-nowrap text-right text-xs uppercase tracking-wide", r === added || r === hot[0] ? "text-accent" : "text-muted")}>row {r}</span>
          {row.map((v, c) => <Cell key={c} value={v} active={(r === hot[0] && c === hot[1]) || r === added} />)}
          <span className="ml-1 text-xs text-muted">{row.length} long</span>
        </motion.div>
      ))}
    </div>
  );
}


// ------------------------------------------------------------------ stack
function StackStage({ s }: { s: State }) {
  const keys = keyed(s.items);
  const top = s.items.length - 1;
  const changed = s.last.op === "push" || s.last.op === "peek" ? top : -1;
  return (
    <motion.ul layout className="flex min-h-56 flex-col-reverse items-center justify-start gap-2 border-b-2 border-border px-10 pb-2">
      <AnimatePresence mode="popLayout">
        {s.items.map((v, i) => (
          <motion.li key={keys[i]} layout initial={{ opacity: 0, y: -60 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -80, transition: { duration: 0.35 } }} transition={spring}
            className="relative">
            <motion.div animate={i === changed ? pulse : {}}
              className={cn("grid h-10 w-28 place-items-center rounded-xl border bg-surface font-heading text-lg font-semibold",
                i === top ? "border-accent" : "border-border")}>
              {v}
            </motion.div>
            {i === top && <span className="absolute top-1/2 left-full ml-3 -translate-y-1/2 text-xs font-medium uppercase tracking-wide text-accent">top</span>}
          </motion.li>
        ))}
      </AnimatePresence>
      {s.items.length === 0 && <Empty text="The stack is empty" />}
    </motion.ul>
  );
}

// ------------------------------------------------------------------ linked list
function LinkedListStage({ s }: { s: State }) {
  const keys = keyed(s.items);
  const op = s.last.op ?? "";
  const found = s.last.found !== false;
  const path = new Set<Label>(op === "search" && found ? s.last.path ?? [] : []);
  const changed = ["insert_head", "insert_tail", "insert_after", "search"].includes(op) && found ? s.last.index ?? -1 : -1;
  const current = s.current_index ?? -1; // the node the walk is standing on
  // the node whose next pointer was just rewired (delete in the middle, insert after / at the tail)
  const rewired = ["delete_value", "insert_after", "insert_tail"].includes(op) && found && s.last.prev != null
    ? s.items.findIndex((v) => v === s.last.prev) : -1;
  const newNodeArrow = op === "insert_after" || op === "insert_head" ? s.last.index ?? -1 : -1;
  return (
    <motion.ul layout className="flex min-h-20 flex-wrap items-start justify-center gap-y-4">
      <AnimatePresence mode="popLayout">
        {s.items.map((v, i) => (
          <motion.li key={keys[i]} layout initial={{ opacity: 0, y: -40 }} animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 50, transition: { duration: 0.35 } }} transition={spring}
            className="flex items-start">
            <Cell value={v} active={i === changed || i === current || i === rewired}
              tone={i === current || path.has(v) ? "path" : i === 0 ? "front" : i === s.items.length - 1 ? "back" : undefined}
              label={nodeLabel(i, s.items.length, i === current, i === rewired)}
              labelTone={i === current || i === rewired ? "accent" : i === 0 ? "accent" : "accent2"} />
            <NextArrow key={`${keys[i]}-${i === rewired || i === newNodeArrow ? s.last.op + String(s.last.value ?? s.last.removed) : "plain"}`}
              hot={i === rewired || i === newNodeArrow} both={s.variant === "doubly" && i < s.items.length - 1} />
          </motion.li>
        ))}
      </AnimatePresence>
      <li className={cn("grid h-12 place-items-center px-1 font-mono text-sm sm:h-14", s.variant === "circular" ? "text-accent2" : "text-muted")}>
        {s.variant === "circular" && s.items.length ? `back to ${s.items[0]}` : "null"}
      </li>
      {s.variant === "doubly" && <li className="w-full text-center text-xs uppercase tracking-wide text-accent2">doubly linked: each box points forward and back</li>}
      {s.variant === "circular" && <li className="w-full text-center text-xs uppercase tracking-wide text-accent2">circular: the tail points back to the head</li>}
    </motion.ul>
  );
}

/** "head", "tail", "current" (walk cursor) and "prev" (pointer just rewired), combined when one node is several. */
function nodeLabel(i: number, n: number, current: boolean, rewired: boolean): string | undefined {
  const parts = [i === 0 && "head", i === n - 1 && "tail", current ? "current" : rewired && "prev"].filter(Boolean);
  return parts.length ? parts.join(" · ") : undefined;
}

/** A node's next pointer. A just-rewired pointer is drawn in the accent colour and redrawn from scratch. */
function NextArrow({ hot, both = false }: { hot: boolean; both?: boolean }) {
  const color = hot ? ACCENT : MUTED;
  return (
    <svg width="40" height="56" viewBox="0 0 40 56" aria-hidden className="shrink-0">
      <motion.line x1="4" y1={both ? 22 : 28} x2="30" y2={both ? 22 : 28} stroke={color} strokeWidth={hot ? 3 : 2}
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: hot ? 0.6 : 0.4 }} />
      <path d={both ? "M28 16 L36 22 L28 28" : "M28 22 L36 28 L28 34"} fill="none" stroke={color} strokeWidth={hot ? 3 : 2} />
      {both && (
        <>
          <line x1="10" y1="34" x2="36" y2="34" stroke={ACCENT2} strokeWidth={2} />
          <path d="M12 28 L4 34 L12 40" fill="none" stroke={ACCENT2} strokeWidth={2} />
        </>
      )}
    </svg>
  );
}

// ------------------------------------------------------------------ binary search tree
function TreeStage({ s, named = [] }: { s: State; named?: string[] }) {
  const W = 640, H = 300, R = 20;
  const nodes = (s.nodes ?? []) as TreeNode[];
  const pos = (n: TreeNode) => ({ x: 30 + n.x * (W - 60), y: 30 + n.y * (H - 70) });
  const byVal = new Map(nodes.map((n) => [n.value, n]));
  const path = new Set(s.last.path ?? []);
  const target = s.last.value;
  const edges = nodes.flatMap((n) =>
    [n.left, n.right].filter((c): c is number => c !== null).map((c) => ({ from: n, to: byVal.get(c)! })));
  if (!nodes.length) return <Empty text="The tree is empty" />;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full max-w-2xl" role="img"
      aria-label={`Binary search tree, in-order: ${s.items.join(", ")}. Root ${s.root}, height ${s.height}.`}>
      {edges.map(({ from, to }) => {
        const a = pos(from), b = pos(to);
        const on = path.has(from.value) && path.has(to.value);
        return (
          <motion.line key={`${from.value}-${to.value}`} initial={{ pathLength: 0, x1: a.x, y1: a.y, x2: b.x, y2: b.y }}
            animate={{ pathLength: 1, x1: a.x, y1: a.y, x2: b.x, y2: b.y }} transition={{ ...spring, pathLength: { duration: 0.6 } }}
            stroke={on ? ACCENT2 : BORDER} strokeWidth={on ? 3 : 2} />
        );
      })}
      {nodes.map((n) => {
        const p = pos(n);
        const isTarget = n.value === target;
        const isLeaf = n.left === null && n.right === null;
        const callLeaf = named.includes("leaf") && isLeaf && n.value !== s.root; // the narration names leaves: show them
        const callRoot = named.includes("root") && n.value === s.root;
        return (
          <motion.g key={n.value} initial={{ opacity: 0, x: p.x, y: p.y - 30 }} animate={{ opacity: 1, x: p.x, y: p.y }} transition={spring}>
            {isTarget && (
              <motion.circle r={R} fill="none" stroke={ACCENT} strokeWidth={2}
                animate={{ r: [R, R + 12], opacity: [0.8, 0] }} transition={{ duration: 1.1, repeat: Infinity }} />
            )}
            {(callLeaf || callRoot) && !isTarget && (
              <motion.circle r={R} fill="none" stroke={ACCENT2} strokeWidth={2}
                animate={{ r: [R, R + 10], opacity: [0.8, 0] }} transition={{ duration: 1.4, repeat: Infinity }} />
            )}
            <circle r={R} fill={isTarget ? ACCENT : SURFACE}
              stroke={path.has(n.value) || callLeaf || callRoot ? ACCENT2 : n.value === s.root ? ACCENT : BORDER} strokeWidth={callLeaf || callRoot ? 3 : 2} />
            <text textAnchor="middle" dy="0.35em" fontSize="15" fontWeight="600" fill={isTarget ? "#000" : TEXT} className="font-heading">{n.value}</text>
            {n.value === s.root && <text textAnchor="middle" y={-R - 8} fontSize="11" fill={callRoot ? ACCENT2 : ACCENT}>ROOT</text>}
            {callLeaf && <text textAnchor="middle" y={R + 16} fontSize="11" fill={ACCENT2}>LEAF</text>}
          </motion.g>
        );
      })}
    </svg>
  );
}

// ------------------------------------------------------------------ graph BFS
function GraphStage({ s }: { s: State }) {
  const W = 640, H = 300, R = 20;
  const nodes = (s.nodes ?? []) as GraphNode[];
  const at = (v: Label) => {
    const n = nodes.find((x) => x.value === v)!;
    return { x: 40 + n.x * (W - 80), y: 20 + n.y * (H - 40) };
  };
  const dfs = s.kind === "graph_dfs";
  const queue = (dfs ? [...(s.stack ?? [])].reverse() : s.queue) ?? []; // DFS: the top of the stack first
  const visited = new Set(s.order ?? []);
  const inQueue = new Set(queue);
  const fresh = new Set(s.last.enqueued ?? []);
  if (!nodes.length) return <Empty text="The graph has no nodes yet" />;
  return (
    <div className="flex w-full flex-col items-center gap-3">
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full max-w-2xl" role="img"
        aria-label={`Graph with nodes ${s.items.join(", ")}. Visited order ${(s.order ?? []).join(", ") || "none yet"}.`}>
        {(s.edges ?? []).map(([u, v]) => {
          const a = at(u), b = at(v);
          const hot = s.current !== null && s.current !== undefined && ((u === s.current && fresh.has(v)) || (v === s.current && fresh.has(u)));
          return (
            <motion.line key={`${u}-${v}`} initial={{ pathLength: 0, x1: a.x, y1: a.y, x2: b.x, y2: b.y }}
              animate={{ pathLength: 1, x1: a.x, y1: a.y, x2: b.x, y2: b.y }} transition={{ ...spring, pathLength: { duration: 0.6 } }}
              stroke={hot ? ACCENT2 : BORDER} strokeWidth={hot ? 3 : 2} />
          );
        })}
        {nodes.map((n) => {
          const p = at(n.value);
          const current = n.value === s.current;
          const fill = current ? ACCENT : visited.has(n.value) ? BORDER : SURFACE;
          return (
            <motion.g key={n.value} initial={{ opacity: 0, x: p.x, y: p.y }} animate={{ opacity: 1, x: p.x, y: p.y }} transition={spring}>
              {current && (
                <motion.circle r={R} fill="none" stroke={ACCENT} strokeWidth={2}
                  animate={{ r: [R, R + 12], opacity: [0.8, 0] }} transition={{ duration: 1.1, repeat: Infinity }} />
              )}
              <circle r={R} fill={fill} stroke={inQueue.has(n.value) ? ACCENT2 : current ? ACCENT : BORDER} strokeWidth={inQueue.has(n.value) ? 3 : 2} />
              <text textAnchor="middle" dy="0.35em" fontSize="15" fontWeight="600" fill={current ? "#000" : TEXT}>{n.value}</text>
            </motion.g>
          );
        })}
      </svg>
      <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-muted">{dfs ? "Stack (top first)" : "Queue"}</span>
          <motion.ul layout className="flex gap-1.5">
            <AnimatePresence mode="popLayout">
              {queue.map((v, i) => (
                <motion.li key={v} layout initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={spring}
                  className={cn("grid size-8 place-items-center rounded-lg border bg-surface font-semibold", i === 0 ? "border-accent" : "border-accent2")}>
                  {v}
                </motion.li>
              ))}
            </AnimatePresence>
            {!queue.length && <li className="text-muted">empty</li>}
          </motion.ul>
        </div>
        <div><span className="text-muted">Visited: </span>{(s.order ?? []).join(" → ") || "none yet"}</div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ bubble sort
function SortStage({ s }: { s: State }) {
  const keys = keyed(s.items);
  const max = Math.max(...s.items.map(Number), 1);
  const compared = new Set(s.last.compared ?? []);
  const sortedFrom = s.sorted_from ?? s.items.length;
  const sortedUpto = s.kind === "insertion_sort" && !s.is_sorted ? s.sorted_upto ?? 0 : 0; // the sorted part so far
  if (!s.items.length) return <Empty text="No list loaded yet" />;
  return (
    <motion.ul layout className="flex h-56 items-end justify-center gap-2 sm:gap-3">
      {s.items.map((v, i) => {
        const isCompared = compared.has(i) && !s.last.finished;
        return (
          <motion.li key={keys[i]} layout transition={spring} className="flex flex-col items-center gap-1.5">
            <motion.div layout animate={isCompared ? pulse : {}} style={{ height: 24 + (Number(v) / max) * 160 }}
              className={cn("flex w-10 items-start justify-center rounded-xl border pt-1.5 font-heading font-semibold sm:w-12",
                i >= sortedFrom ? "border-accent2 bg-accent2/20" : i < sortedUpto ? "border-accent2/60 bg-surface" : "border-border bg-surface",
                isCompared && "border-accent")}>
              {v}
            </motion.div>
            <span className={cn("h-4 text-xs uppercase", isCompared ? "text-accent" : i >= sortedFrom ? "text-accent2" : "text-transparent")}>
              {isCompared ? (s.last.swapped ? "swap" : "ok") : i >= sortedFrom ? "done" : "."}
            </span>
          </motion.li>
        );
      })}
    </motion.ul>
  );
}

// ------------------------------------------------------------------ complexity: live work counter and growth table
const UNITS: Record<string, string> = { bubble_sort: "comparisons", insertion_sort: "comparisons", linear_search: "comparisons",
  linked_list_search: "comparisons" };

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-muted">{label}</span>
      <motion.span key={`${label}-${value}`} initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}
        className="font-heading text-lg font-semibold tabular-nums text-accent">{value}</motion.span>
    </div>
  );
}

/** The real work counted so far: comparisons (with a per-pass tally), items checked, BFS visits and checks, items touched. */
function WorkMeter({ s }: { s: State }) {
  const l = s.last;
  let body: ReactNode = null;
  if ((s.kind === "bubble_sort" || s.kind === "insertion_sort") && s.items.length) {
    const passes = s.pass_counts ?? [];
    body = (
      <>
        <Metric label="comparisons" value={s.comparisons ?? 0} />
        {passes.length > 0 && (
          <ul className="flex flex-wrap items-center gap-1.5" aria-label="Comparisons per pass">
            {passes.map((c, i) => (
              <li key={i} className={cn("rounded-lg border px-2 py-0.5 tabular-nums",
                i === passes.length - 1 && !s.is_sorted ? "border-accent text-text" : "border-accent2/60 text-muted")}>
                {s.kind === "insertion_sort" ? "item" : "pass"} {i + 1}: <span className="font-semibold text-text">{c}</span>
              </li>
            ))}
            {passes.length > 1 && <li className="tabular-nums text-muted">= {passes.reduce((a, b) => a + b, 0)}</li>}
          </ul>
        )}
      </>
    );
  } else if ((s.kind === "graph_bfs" || s.kind === "graph_dfs") && (s.visits ?? 0) > 0) {
    body = (
      <>
        <Metric label="visits" value={s.visits ?? 0} />
        <Metric label="neighbour checks" value={s.checks ?? 0} />
        <Metric label="total" value={(s.visits ?? 0) + (s.checks ?? 0)} />
      </>
    );
  } else if (typeof l.checked === "number" && (l.op === "scan" || l.op === "walk")) {
    body = <Metric label="comparisons" value={l.checked} />;
  } else if (typeof l.touched === "number") {
    body = <Metric label="items touched" value={l.touched} />;
  }
  if (!body) return null;
  return <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm" aria-live="polite">{body}</div>;
}

/** Growth table: the real count for each input size n, with a bar on a log scale so 6 and 4950 both stay readable. */
function GrowthStage({ s }: { s: State }) {
  const rows = s.rows ?? [];
  if (!rows.length) return <Empty text="No counts yet" />;
  const unit = UNITS[s.algo ?? ""] ?? "steps";
  const max = Math.log10(Math.max(...rows.map((r) => r.count), 1) + 1);
  return (
    <div className="w-full max-w-xl">
      <table className="w-full border-separate border-spacing-y-2 text-sm">
        <caption className="pb-2 text-left text-xs text-muted">Counted by running the real algorithm (worst case)</caption>
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-muted">
            <th scope="col" className="w-16 font-medium">n</th>
            <th scope="col" className="w-24 font-medium">{unit}</th>
            <th scope="col" className="font-medium"><span className="sr-only">relative size</span></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <motion.tr key={r.n} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ ...spring, delay: i * 0.35 }}>
              <td className="font-heading font-semibold tabular-nums">{r.n}</td>
              <td className="font-heading font-semibold tabular-nums text-accent">{r.count}</td>
              <td>
                <motion.div initial={{ width: 0 }} animate={{ width: `${Math.max(4, (Math.log10(r.count + 1) / max) * 100)}%` }}
                  transition={{ duration: 0.6, delay: i * 0.35 }} className="h-3 rounded-full bg-accent2/70" />
              </td>
            </motion.tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Stage({ state: raw, showWork = false, named }: { state: State; showWork?: boolean; named?: string[] }) {
  // lessons saved before `minimize: false` lost empty `last: {}` objects; treat a missing one as "no op yet"
  const state = raw.last ? raw : { ...raw, last: {} };
  const view = (() => {
    switch (state.kind) {
      case "array": return <ArrayStage s={state} />;
      case "queue": return <QueueStage s={state} />;
      case "stack": return <StackStage s={state} />;
      case "linked_list": return <LinkedListStage s={state} />;
      case "binary_tree": return <TreeStage s={state} named={named} />;
      case "array_2d": return <GridStage s={state} />;
      case "dyn_array": return <DynArrayStage s={state} />;
      case "jagged_array": return <JaggedStage s={state} />;
      case "graph_bfs": case "graph_dfs": return <GraphStage s={state} />;
      case "bubble_sort": case "insertion_sort": return <SortStage s={state} />;
      case "growth": return <GrowthStage s={state} />;
    }
  })();
  // the live counter: always for bubble sort (comparisons are its work), and for every structure in a complexity lesson
  const counted = state.kind === "bubble_sort" || state.kind === "insertion_sort";
  if (!(showWork || counted) || state.kind === "growth") return view;
  return (
    <div className="flex w-full flex-col items-center gap-5">
      {view}
      <WorkMeter s={state} />
    </div>
  );
}

/** One-line caption of what the last op did, from the true state. */
export function opCaption(s: State): string {
  const l = s.last ?? {};
  switch (l.op) {
    case "append": return l.refused ? `${l.value} refused: the array is full`
      : l.resized ? `full: ${l.old_capacity} → ${l.new_capacity} slots, copy ${l.copied}, append ${l.value}` : `append ${l.value} at [${l.index}]`;
    case "insert_at": return `insert ${l.value} at [${l.index}]${l.shifted ? `, shift ${l.shifted} right` : ""}`;
    case "delete_at": return `delete [${l.index}] = ${l.removed}${l.shifted ? `, shift ${l.shifted} left` : ""}`;
    case "set": return `set [${l.index}]: ${l.old} → ${l.value}`;
    case "get": return `get [${l.index}] → ${l.value}`;
    case "scan": return `compare [${l.index}] = ${l.value} with ${l.target}${l.found ? " → found" : ""}`;
    case "reload": return `new input ${l.values?.join(", ")}`;
    case "grid": return `2D array ${s.cells?.length ?? 0} x ${s.cols ?? 0}`;
    case "get2": return `get [${l.row}][${l.col}] → ${l.value}`;
    case "set2": return `set [${l.row}][${l.col}]: ${l.old} → ${l.value}`;
    case "row": return `add row ${l.row} (${l.length} long)`;
    case "init_static": return `static array, ${s.capacity} slots`;
    case "init_dynamic": return `dynamic array, ${s.capacity} slots`;
    case "variant": return `${l.variant} ${s.kind.replace("_", " ")}`;
    case "push_front": return `push ${l.value} at the front`;
    case "pop_back": return `pop ${l.removed} from the back`;
    case "reset": return "new graph";
    case "init": return s.kind === "linked_list"
      ? `init head → ${[...(l.values ?? []), "null"].join(" → ")}` : `init ${l.values?.join(", ")}`;
    case "walk": return `walk to ${l.value} · ${l.value}.next → ${l.next ?? "null"}`;
    case "insert_after": return `insert ${l.value} after ${l.prev} · ${l.prev}.next → ${l.value}`;
    case "enqueue": case "push": case "insert_head": case "insert_tail": case "insert_bst":
      return `${l.op.replace("_", " ")} ${l.value}`;
    case "dequeue": case "pop": return `${l.op} → removed ${l.removed}`;
    case "delete_value":
      if (l.found === false) return `delete ${l.value}: not found, reached null`;
      return l.prev != null ? `delete ${l.removed} · ${l.prev}.next → ${l.next ?? "null"}` : `delete ${l.removed} · head → ${l.next ?? "null"}`;
    case "peek": return `peek → ${l.value}`;
    case "search":
      return l.found === false ? `search ${l.value}: not found, reached null` : `search ${l.value}: ${(l.path ?? []).join(" → ")}`;
    case "search_bst": return `search ${l.value}: ${(l.path ?? []).join(" → ")}`;
    case "add_edge": return `add edge ${l.edge?.join("–")}`;
    case "start_bfs": return `start BFS at ${l.value}`;
    case "start_dfs": return `start DFS at ${l.value}`;
    case "visit": return l.pushed ? `visit ${l.removed}${l.pushed.length ? `, push ${l.pushed.join(", ")}` : ", backtrack"}`
      : `visit ${l.removed}${l.enqueued?.length ? `, enqueue ${l.enqueued.join(", ")}` : ""}`;
    case "load": return `load ${l.values?.join(", ")}`;
    case "step": case "compare": case "swap":
      return l.finished ? "already sorted" : `compare ${l.values?.join(" and ")}${l.swapped ? " → swap" : ""}`;
    default: return s.kind === "growth" ? `count ${s.algo?.replaceAll("_", " ")} for n = ${(s.rows ?? []).map((r) => r.n).join(", ")}` : "";
  }
}
