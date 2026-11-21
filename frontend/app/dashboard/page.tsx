import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, Plus, Sparkles } from "lucide-react";
import { LessonsPanel } from "@/components/dashboard/lessons-panel";
import { QuizHistory } from "@/components/dashboard/quiz-history";
import { RetryNotice } from "@/components/dashboard/retry-notice";
import { StatCards, type DashboardStats } from "@/components/dashboard/stat-cards";
import { DASHBOARD_TOPICS, listLessons, listQuizResults, type LessonSummary, type QuizRow } from "@/lib/data";
import { AppNav } from "@/components/app-nav";
import { DotPattern } from "@/components/ui/dot-pattern";
import { Skeleton } from "@/components/ui/skeleton";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = { title: "Dashboard | Structura" };

const QUICK_TOPICS = ["how does a queue work", "show BFS on a graph", "explain a linked list delete"];

async function Greeting() {
  const user = await requireUser();
  const first = user.name.split(" ")[0] || "there";
  return (
    <div>
      <p className="eyebrow mb-3"><span className="h-px w-6 bg-accent" aria-hidden />Dashboard</p>
      <h1 className="text-title">Welcome back, {first}.</h1>
      <p className="mt-2 text-muted">Signed in as {user.email}</p>
    </div>
  );
}

function GreetingSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-label="Loading" role="status">
      <Skeleton className="h-3 w-24 bg-surface" />
      <Skeleton className="h-10 w-72 max-w-full bg-surface" />
      <Skeleton className="h-4 w-56 bg-surface" />
    </div>
  );
}

/** Shown when the user has no saved lessons yet. */
function EmptyLessons() {
  return (
    <section aria-labelledby="lessons-title" className="relative isolate overflow-hidden rounded-3xl border border-border bg-surface px-6 py-14 text-center sm:px-12">
      <DotPattern width={20} height={20} cr={1} className="-z-10 text-border [mask-image:radial-gradient(ellipse_at_center,black_10%,transparent_65%)]" />
      <div className="mx-auto mb-6 grid size-14 place-items-center rounded-2xl border border-border bg-background">
        <BookOpen className="size-6 text-accent" aria-hidden />
      </div>
      <h2 id="lessons-title" className="text-2xl font-semibold">No saved lessons yet</h2>
      <p className="mx-auto mt-2 max-w-md text-muted">
        Generate your first lesson. It is saved here automatically, ready to replay without regenerating.
      </p>
      <Link href="/app"
        className="group mt-8 inline-flex h-12 items-center gap-2 rounded-xl bg-accent px-6 font-semibold text-on-accent shadow-[0_10px_40px_-12px_rgba(255,122,26,0.6)] transition-[transform,background-color] hover:-translate-y-0.5 hover:bg-accent/95 active:scale-[0.97]">
        <Plus className="size-4" aria-hidden /> Create new lesson
      </Link>
      <div className="mt-10">
        <p className="mb-3 text-xs text-muted">Or start from an example</p>
        <ul className="flex flex-wrap justify-center gap-2">
          {QUICK_TOPICS.map((t) => (
            <li key={t}>
              <Link href={`/app?topic=${encodeURIComponent(t)}`}
                className="group inline-flex items-center gap-2 rounded-full border border-border bg-background px-3.5 py-2 text-sm transition-colors hover:border-accent2 hover:text-accent2">
                <Sparkles className="size-3.5 text-accent" aria-hidden />{t}
                <ArrowRight className="size-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function computeStats(lessons: LessonSummary[], quiz: QuizRow[]): DashboardStats {
  const covered = new Set(lessons.map((l) => l.structure).filter((s) => (DASHBOARD_TOPICS as readonly string[]).includes(s)));
  const pct = quiz.length ? Math.round((quiz.reduce((a, q) => a + q.score / q.total, 0) / quiz.length) * 100) : null;
  const dates = [...lessons.map((l) => l.updatedAt), ...quiz.map((q) => q.createdAt)].sort();
  return { lessons: lessons.length, topicsCovered: covered.size, topicsTotal: DASHBOARD_TOPICS.length, avgScore: pct, lastActivity: dates.at(-1) ?? null };
}

async function DashboardData() {
  const user = await requireUser();
  let lessons: LessonSummary[], quiz: QuizRow[];
  try {
    [lessons, quiz] = await Promise.all([listLessons(user.id), listQuizResults(user.id)]);
  } catch (err) {
    console.error("[dashboard] database read failed:", err instanceof Error ? `${err.name}: ${err.message}` : err);
    return <RetryNotice />;
  }
  return (
    <>
      <StatCards stats={computeStats(lessons, quiz)} />
      {lessons.length ? <LessonsPanel initial={lessons} /> : <EmptyLessons />}
      <QuizHistory rows={quiz} />
    </>
  );
}

function DataSkeleton() {
  return (
    <div className="flex flex-col gap-10" role="status" aria-label="Loading your dashboard">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28 rounded-2xl bg-surface" />)}
      </div>
      <Skeleton className="h-8 w-48 bg-surface" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-44 rounded-2xl bg-surface" />)}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <>
      <AppNav current="dashboard" />
      <main className="container-page flex flex-col gap-10 py-12 lg:py-16">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <Suspense fallback={<GreetingSkeleton />}>
            <Greeting />
          </Suspense>
          <Link href="/app"
            className="inline-flex h-11 items-center gap-2 rounded-xl border border-border bg-surface px-5 text-sm font-medium transition-[transform,border-color,color] hover:-translate-y-0.5 hover:border-accent hover:text-accent active:scale-[0.97]">
            <Plus className="size-4" aria-hidden /> New lesson
          </Link>
        </div>
        <Suspense fallback={<DataSkeleton />}>
          <DashboardData />
        </Suspense>
      </main>
    </>
  );
}
