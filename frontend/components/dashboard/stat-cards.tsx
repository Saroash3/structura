"use client";

import { useEffect, useState } from "react";
import { BookOpen, Clock, Layers, Target, type LucideIcon } from "lucide-react";
import { NumberTicker } from "@/components/ui/number-ticker";

export type DashboardStats = {
  lessons: number;
  topicsCovered: number;
  topicsTotal: number;
  avgScore: number | null; // percent
  lastActivity: string | null; // ISO date
};

/** "3 hours ago" etc. Computed after mount so server and client HTML match. */
function useRelativeTime(iso: string | null): string {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0);
    const t = setInterval(tick, 60_000);
    return () => { clearTimeout(first); clearInterval(t); };
  }, []);
  if (!iso) return "No activity yet";
  if (now === null) return " ";
  const secs = Math.round((new Date(iso).getTime() - now) / 1000);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const units: [Intl.RelativeTimeFormatUnit, number][] = [["day", 86400], ["hour", 3600], ["minute", 60]];
  const unit = units.find(([, s]) => Math.abs(secs) >= s);
  return unit ? rtf.format(Math.round(secs / unit[1]), unit[0]) : "just now";
}

function Card({ icon: Icon, label, children }: { icon: LucideIcon; label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-border bg-surface p-5 transition-colors hover:border-border/100">
      <div className="flex items-center justify-between">
        <dt className="text-sm text-muted">{label}</dt>
        <Icon className="size-4 text-accent" aria-hidden />
      </div>
      <dd className="font-heading text-3xl font-semibold tracking-tight sm:text-4xl">{children}</dd>
    </div>
  );
}

export function StatCards({ stats }: { stats: DashboardStats }) {
  const last = useRelativeTime(stats.lastActivity);
  return (
    <dl className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <Card icon={BookOpen} label="Lessons created"><NumberTicker value={stats.lessons} /></Card>
      <Card icon={Layers} label="Topics covered">
        <NumberTicker value={stats.topicsCovered} /><span className="text-lg text-muted"> / {stats.topicsTotal}</span>
      </Card>
      <Card icon={Target} label="Average quiz score">
        {stats.avgScore === null ? <span className="text-muted">-</span> : <><NumberTicker value={stats.avgScore} /><span className="text-accent">%</span></>}
      </Card>
      <Card icon={Clock} label="Last activity"><span className="text-xl sm:text-2xl">{last}</span></Card>
    </dl>
  );
}
