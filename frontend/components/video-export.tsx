"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Download, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cancelExport, exportStatus, startExport, videoUrl, type ExportJob } from "@/lib/video-api";
import type { Lesson } from "@/lib/types";

const STAGE_LABEL: Record<ExportJob["stage"], string> = {
  queued: "Waiting to start",
  rendering: "Rendering the animation",
  voicing: "Adding the voice",
  done: "Done",
  error: "Failed",
  cancelled: "Cancelled",
};
const PREFETCH_DELAY_MS = 2500; // after a lesson appears (or is revised), its MP4 is made in the background

function mb(bytes?: number) {
  return bytes ? `${(bytes / 1_000_000).toFixed(1)} MB` : "";
}

/**
 * "Download video": the MP4 is usually made in the background right after the lesson appears, so the click is instant.
 * Otherwise the click joins (or starts) the export and shows its real progress, with a Cancel button.
 */
export function VideoExport({ lesson, lessonId }: { lesson: Lesson; lessonId: string | null }) {
  const [job, setJob] = useState<ExportJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const idRef = useRef(lessonId);
  useEffect(() => { idRef.current = lessonId; }, [lessonId]);

  // a revised lesson is a different video: forget the finished job (the background export below makes the new one)
  const [forLesson, setForLesson] = useState(lesson);
  if (forLesson !== lesson) {
    setForLesson(lesson);
    setJob(null);
    setError(null);
    setBusy(false);
  }

  // background pre-render (low priority on the backend: a Download of another lesson cancels it)
  useEffect(() => {
    const t = setTimeout(() => {
      startExport(lesson, idRef.current, true).then((j) => setJob((cur) => cur ?? (j.stage === "done" ? j : null))).catch(() => {});
    }, PREFETCH_DELAY_MS);
    return () => clearTimeout(t);
  }, [lesson]);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  function download(j: ExportJob) {
    const a = document.createElement("a");
    a.href = videoUrl(j.id);
    a.download = j.filename ?? "structura-lesson.mp4";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  async function poll(id: string) {
    try {
      const j = await exportStatus(id);
      setJob(j);
      if (j.stage === "done") {
        setBusy(false);
        download(j);
      } else if (j.stage === "error" || j.stage === "cancelled") {
        setBusy(false);
        if (j.stage === "error") setError(j.message);
      } else {
        timer.current = setTimeout(() => void poll(id), 700);
      }
    } catch (e) {
      setBusy(false);
      setError(e instanceof Error ? e.message : "The video export failed.");
    }
  }

  async function onClick() {
    if (job?.stage === "done") return download(job);
    setBusy(true);
    setError(null);
    try {
      const j = await startExport(lesson, lessonId); // joins the background export of this lesson if it is running
      setJob(j);
      if (j.stage === "done") {
        setBusy(false);
        download(j);
      } else {
        void poll(j.id);
      }
    } catch (e) {
      setBusy(false);
      setError(e instanceof Error ? e.message : "The video export failed.");
    }
  }

  async function onCancel() {
    if (timer.current) clearTimeout(timer.current);
    setBusy(false);
    if (job) {
      try {
        setJob(await cancelExport(job.id));
      } catch {
        // the export may have just finished; nothing to undo
      }
    }
  }

  const pct = Math.round((job?.progress ?? 0) * 100);
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" onClick={() => void onClick()} disabled={busy} className="h-10 px-4 font-semibold">
          {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Download aria-hidden />}
          Download video
        </Button>
        {busy && (
          <Button type="button" variant="outline" onClick={() => void onCancel()} className="h-10 px-3">
            <X aria-hidden /> Cancel
          </Button>
        )}
        <p className="text-sm text-muted">
          {busy && job ? `${STAGE_LABEL[job.stage]}… ${pct}%`
            : job?.stage === "done" ? <span className="inline-flex items-center gap-1.5 text-accent2">
                <CheckCircle2 className="size-4" aria-hidden />MP4 ready{job.duration ? `, ${Math.round(job.duration)} s` : ""}{job.size ? `, ${mb(job.size)}` : ""}
              </span>
            : job?.stage === "cancelled" ? "Export cancelled."
            : "An MP4 of this lesson with its voice and a quiz summary, made on this computer."}
        </p>
      </div>
      {busy && (
        <div className="h-1.5 overflow-hidden rounded-full bg-border" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}
          aria-label="Video export progress">
          <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${pct}%` }} />
        </div>
      )}
      {error && (
        <p role="alert" className="flex items-start gap-2 text-sm text-destructive">
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />{error}
        </p>
      )}
    </div>
  );
}
