import "server-only";
import { isValidObjectId } from "mongoose";
import { connectDB } from "@/lib/db";
import { Lesson, QuizResult, User } from "@/lib/models";
import type { Lesson as LessonPayload } from "@/lib/types";

/**
 * Data Access Layer. EVERY function takes the signed-in user's id (from requireUser / requireApiUser)
 * and scopes its query to it, so one user can never read or change another user's data.
 */

export const DASHBOARD_TOPICS = ["linked_list", "stack", "queue", "binary_tree", "graph_bfs"] as const;

export type LessonSummary = {
  id: string;
  title: string;
  topic: string;
  structure: string;
  level: string;
  pinned: boolean;
  scenes: number;
  duration: number;
  createdAt: string;
  updatedAt: string;
};

export type QuizRow = { id: string; lessonId: string | null; topic: string; structure: string; score: number; total: number; createdAt: string };

const iso = (d: Date | string | undefined) => new Date(d ?? 0).toISOString();

/**
 * Runs a READ query, retrying once on failure. A Wi-Fi blip can leave the driver waiting on dead sockets until the
 * query fails (~15 s); by then it has reconnected, so an immediate second try usually succeeds in well under a second.
 * Only for reads: repeating them is harmless.
 */
async function read<T>(query: () => Promise<T>): Promise<T> {
  await connectDB();
  try {
    return await query();
  } catch (err) {
    console.warn("[db] read failed, retrying once:", err instanceof Error ? `${err.name}: ${err.message}` : err);
    await connectDB();
    return await query();
  }
}

// ---------------------------------------------------------------- lessons
function contentFields(lesson: LessonPayload) {
  return {
    topic: lesson.topic,
    structure: lesson.structure,
    level: lesson.level === "intermediate" ? ("intermediate" as const) : ("beginner" as const),
    plan: lesson.plan,
    audioDurations: lesson.scenes.map((s) => s.duration),
    snapshot: lesson,
  };
}

export async function createLesson(userId: string, lesson: LessonPayload): Promise<string> {
  await connectDB();
  const doc = await Lesson.create({ userId, title: lesson.plan.topic || lesson.topic, ...contentFields(lesson) });
  return String(doc._id);
}

/** Replace a saved lesson's content (used after a revision). Returns false if not found for this user. */
export async function updateLessonContent(userId: string, id: string, lesson: LessonPayload): Promise<boolean> {
  if (!isValidObjectId(id)) return false;
  await connectDB();
  const res = await Lesson.updateOne({ _id: id, userId }, { $set: contentFields(lesson) });
  return res.matchedCount === 1;
}

export async function listLessons(userId: string): Promise<LessonSummary[]> {
  const docs = await read(() => Lesson.find({ userId })
    .select("title topic structure level pinned audioDurations createdAt updatedAt")
    .sort({ pinned: -1, updatedAt: -1 })
    .lean());
  return docs.map((d) => ({
    id: String(d._id),
    title: d.title,
    topic: d.topic,
    structure: d.structure,
    level: d.level ?? "beginner",
    pinned: Boolean(d.pinned),
    scenes: d.audioDurations?.length ?? 0,
    duration: Math.round((d.audioDurations ?? []).reduce((a, b) => a + b, 0)),
    createdAt: iso(d.createdAt),
    updatedAt: iso(d.updatedAt),
  }));
}

export async function getLesson(userId: string, id: string): Promise<{ id: string; title: string; snapshot: LessonPayload } | null> {
  if (!isValidObjectId(id)) return null;
  const d = await read(() => Lesson.findOne({ _id: id, userId }).select("title snapshot").lean());
  if (!d?.snapshot) return null;
  // plain JSON so it can be handed to a Client Component
  return { id: String(d._id), title: d.title, snapshot: JSON.parse(JSON.stringify(d.snapshot)) as LessonPayload };
}

export async function patchLesson(userId: string, id: string, patch: { title?: string; pinned?: boolean }): Promise<boolean> {
  if (!isValidObjectId(id)) return false;
  await connectDB();
  const res = await Lesson.updateOne({ _id: id, userId }, { $set: patch }, { timestamps: false });
  return res.matchedCount === 1;
}

export async function deleteLesson(userId: string, id: string): Promise<boolean> {
  if (!isValidObjectId(id)) return false;
  await connectDB();
  const res = await Lesson.deleteOne({ _id: id, userId });
  return res.deletedCount === 1;
}

// ---------------------------------------------------------------- quiz results
export async function createQuizResult(
  userId: string,
  r: { lessonId?: string | null; topic: string; structure?: string; score: number; total: number },
): Promise<string> {
  await connectDB();
  // only link lessons that belong to this user
  const lessonId = r.lessonId && isValidObjectId(r.lessonId) && (await Lesson.exists({ _id: r.lessonId, userId })) ? r.lessonId : undefined;
  const doc = await QuizResult.create({ userId, lessonId, topic: r.topic, structure: r.structure, score: r.score, total: r.total });
  return String(doc._id);
}

export async function listQuizResults(userId: string, limit = 50): Promise<QuizRow[]> {
  const docs = await read(() => QuizResult.find({ userId }).sort({ createdAt: -1 }).limit(limit).lean());
  return docs.map((d) => ({
    id: String(d._id),
    lessonId: d.lessonId ? String(d.lessonId) : null,
    topic: d.topic,
    structure: d.structure ?? "",
    score: d.score,
    total: d.total,
    createdAt: iso(d.createdAt),
  }));
}

// ---------------------------------------------------------------- profile
export async function getProfile(userId: string) {
  const u = await read(() => User.findById(userId).select("name email level createdAt").lean());
  return u ? { name: u.name, email: u.email, level: (u.level ?? "beginner") as "beginner" | "intermediate", createdAt: iso(u.createdAt) } : null;
}

export async function getPasswordHash(userId: string): Promise<string | null> {
  await connectDB();
  const u = await User.findById(userId).select("passwordHash").lean();
  return u?.passwordHash ?? null;
}

export async function updateProfile(userId: string, patch: { name?: string; level?: "beginner" | "intermediate"; passwordHash?: string }) {
  await connectDB();
  await User.updateOne({ _id: userId }, { $set: patch });
}

/** Deletes the user and everything they own. */
export async function deleteAccount(userId: string) {
  await connectDB();
  await Promise.all([Lesson.deleteMany({ userId }), QuizResult.deleteMany({ userId })]);
  await User.deleteOne({ _id: userId });
}
