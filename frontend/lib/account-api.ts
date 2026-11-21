import type { Lesson } from "./types";

/** Same-origin calls to the Next.js API routes (session cookie is sent automatically). */
async function call<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = (await res.json().catch(() => ({}))) as { error?: string } & T;
  if (!res.ok) throw new Error(data.error ?? `Request failed (${res.status}).`);
  return data;
}

export const saveLesson = (lesson: Lesson) => call<{ id: string }>("/api/lessons", "POST", lesson);
export const updateSavedLesson = (id: string, lesson: Lesson) => call<{ ok: true }>(`/api/lessons/${id}`, "PUT", lesson);
export const patchLesson = (id: string, patch: { title?: string; pinned?: boolean }) => call<{ ok: true }>(`/api/lessons/${id}`, "PATCH", patch);
export const deleteLesson = (id: string) => call<{ ok: true }>(`/api/lessons/${id}`, "DELETE");
export const saveQuizResult = (r: { lessonId: string | null; topic: string; structure: string; score: number; total: number }) =>
  call<{ id: string }>("/api/quiz-results", "POST", r);
