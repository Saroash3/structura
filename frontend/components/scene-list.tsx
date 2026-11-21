"use client";

import { BadgeCheck, Gauge } from "lucide-react";
import type { Scene } from "@/lib/types";
import { cn } from "@/lib/utils";

export function SceneList({ scenes, active, onSelect, revisedId }: {
  scenes: Scene[];
  active: number;
  onSelect: (i: number) => void;
  revisedId?: number;
}) {
  return (
    <section aria-labelledby="scenes-title" className="rounded-xl border border-border bg-surface p-4">
      <h2 id="scenes-title" className="mb-3 text-lg font-semibold">Scenes</h2>
      <ol className="flex max-h-[28rem] flex-col gap-1.5 overflow-y-auto pr-1">
        {scenes.map((s, i) => (
          <li key={s.id}>
            <button type="button" onClick={() => onSelect(i)} aria-current={i === active ? "step" : undefined}
              className={cn(
                "flex w-full items-start gap-3 rounded-lg border px-3 py-2 text-left transition-colors",
                i === active ? "border-accent bg-accent/10" : "border-transparent hover:border-border hover:bg-background",
              )}>
              <span className={cn("mt-0.5 grid size-6 shrink-0 place-items-center rounded-md text-xs font-semibold",
                i === active ? "bg-accent text-on-accent" : "bg-background text-muted")}>
                {s.id}
              </span>
              <span className="min-w-0 flex-1">
                <span className="line-clamp-2 text-sm text-text">{s.narration}</span>
                <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                  <span className="font-mono">{s.ops.length ? s.ops.map((o) => `${o.op}(${o.args.join(", ")})`).join(" ") : "no ops"}</span>
                  <span>{(s.duration / s.speed).toFixed(1)}s</span>
                  {s.speed !== 1 && <span className="inline-flex items-center gap-1 text-accent2"><Gauge className="size-3" aria-hidden />{s.speed}x</span>}
                  {s.id === revisedId && <span className="text-accent2">revised</span>}
                  {s.verified && (
                    <span className="inline-flex items-center gap-1 text-accent2" title={`Narration source: ${s.narration_source}`}>
                      <BadgeCheck className="size-3.5" aria-hidden /> Verified
                    </span>
                  )}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
