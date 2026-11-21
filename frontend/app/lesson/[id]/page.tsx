import { Suspense } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AlertCircle } from "lucide-react";
import { AppNav } from "@/components/app-nav";
import { LessonViewer } from "@/components/lesson-viewer";
import { Skeleton } from "@/components/ui/skeleton";
import { getLesson } from "@/lib/data";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = { title: "Lesson | Structura" };

async function SavedLesson({ params }: { params: Promise<{ id: string }> }) {
  const [{ id }, user] = await Promise.all([params, requireUser()]);
  let lesson: Awaited<ReturnType<typeof getLesson>>;
  try {
    lesson = await getLesson(user.id, id); // scoped to this user: someone else's id is "not found"
  } catch {
    return (
      <div role="alert" className="flex items-start gap-3 rounded-2xl border border-destructive/60 bg-destructive/10 p-5">
        <AlertCircle className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
        <div>
          <p className="font-semibold">Could not load this lesson</p>
          <p className="text-sm text-muted">The database is unavailable right now. <Link href="/dashboard" className="text-accent2 underline">Back to dashboard</Link></p>
        </div>
      </div>
    );
  }
  if (!lesson) notFound();
  return <LessonViewer id={lesson.id} title={lesson.title} lesson={lesson.snapshot} />;
}

function LessonSkeleton() {
  return (
    <div className="flex flex-col gap-6" role="status" aria-label="Loading lesson">
      <Skeleton className="h-4 w-36 bg-surface" />
      <Skeleton className="h-10 w-80 max-w-full bg-surface" />
      <Skeleton className="h-[30rem] rounded-2xl bg-surface" />
    </div>
  );
}

export default function LessonPage({ params }: PageProps<"/lesson/[id]">) {
  return (
    <>
      <AppNav />
      <main className="container-page py-10 lg:py-14">
        <Suspense fallback={<LessonSkeleton />}>
          <SavedLesson params={params} />
        </Suspense>
      </main>
    </>
  );
}
