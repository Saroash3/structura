import { API_URL } from "./api";
import type { Lesson } from "./types";

/** A video export job on the backend (see backend/video.py). */
export type ExportJob = {
  id: string;
  stage: "queued" | "rendering" | "voicing" | "done" | "error" | "cancelled";
  progress: number;
  message: string;
  cached: boolean;
  duration?: number;
  size?: number;
  filename?: string;
  prefetch?: boolean;
  /** how long the export took, in seconds */
  seconds?: number;
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new Error("Could not reach the backend. Is it running?");
  }
  const data = (await res.json().catch(() => null)) as (T & { message?: string }) | null;
  if (!res.ok || !data) throw new Error(data?.message || "The video export failed. Please try again.");
  return data;
}

/** Start exporting (or reuse the cached MP4). The backend renders from this frontend's /render page. */
export function startExport(lesson: Lesson, lessonId: string | null, prefetch = false): Promise<ExportJob> {
  const { topic, structure, scenes, quiz, analysis } = lesson;
  return call<ExportJob>("/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lesson: { topic, structure, scenes, quiz, analysis }, origin: window.location.origin, lesson_id: lessonId, prefetch }),
  });
}

export function cancelExport(id: string): Promise<ExportJob> {
  return call<ExportJob>(`/export/${encodeURIComponent(id)}/cancel`, { method: "POST" });
}

export function exportStatus(id: string): Promise<ExportJob> {
  return call<ExportJob>(`/export/${encodeURIComponent(id)}`);
}

export function videoUrl(id: string): string {
  return `${API_URL}/export/${encodeURIComponent(id)}/video`;
}
