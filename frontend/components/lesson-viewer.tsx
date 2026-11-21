"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, BadgeCheck } from "lucide-react";
import { Player } from "@/components/player";
import { Quiz } from "@/components/quiz";
import { VideoExport } from "@/components/video-export";
import { SceneList } from "@/components/scene-list";
import { saveQuizResult } from "@/lib/account-api";
import { structureLabel } from "@/lib/structure-labels";
import type { Lesson } from "@/lib/types";

type QuizState = "idle" | "saving" | "saved" | "error";

/** Replays a saved lesson from its stored snapshot. Nothing is regenerated. */
export function LessonViewer({ id, title, lesson }: { id: string; title: string; lesson: Lesson }) {
  const [sceneIdx, setSceneIdx] = useState(0);
  const [quiz, setQuiz] = useState<QuizState>("idle");

  async function onQuizComplete(score: number, total: number) {
    setQuiz("saving");
    try {
      await saveQuizResult({ lessonId: id, topic: title, structure: lesson.structure, score, total });
      setQuiz("saved");
    } catch {
      setQuiz("error");
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-4">
        <Link href="/dashboard" className="inline-flex w-fit items-center gap-1.5 text-sm text-muted transition-colors hover:text-text">
          <ArrowLeft className="size-4" aria-hidden /> Back to dashboard
        </Link>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="eyebrow mb-3"><span className="h-px w-6 bg-accent" aria-hidden />Saved lesson</p>
            <h1 className="text-title">{title}</h1>
          </div>
          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
            <span>{structureLabel(lesson.structure)}</span>&middot;<span>{lesson.scenes.length} steps</span>&middot;
            <span className="inline-flex items-center gap-1 text-accent2"><BadgeCheck className="size-4" aria-hidden />all verified</span>
          </p>
        </div>
      </div>

      <Player lesson={lesson} sceneIdx={sceneIdx} onSceneChange={setSceneIdx} />
      <VideoExport lesson={lesson} lessonId={id} />
      <div className="grid gap-6 xl:grid-cols-2">
        <SceneList scenes={lesson.scenes} active={sceneIdx} onSelect={setSceneIdx} />
        {lesson.quiz && (
          <Quiz questions={lesson.quiz} lessonKey={id} onComplete={onQuizComplete}
            status={
              quiz === "saving" ? <span className="text-muted">Saving result...</span>
              : quiz === "saved" ? <Link href="/dashboard" className="text-accent2 hover:underline">Saved to your quiz history</Link>
              : quiz === "error" ? <span className="text-destructive">Result not saved. Check your connection.</span>
              : null
            } />
        )}
      </div>
    </div>
  );
}
