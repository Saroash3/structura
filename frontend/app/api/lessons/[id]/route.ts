import { apiUserId, dbDown, json, notFound, readJson, unauthorized } from "@/lib/api-auth";
import { deleteLesson, patchLesson, updateLessonContent } from "@/lib/data";
import type { Lesson } from "@/lib/types";
import { lessonPatchSchema, lessonPayloadSchema } from "@/lib/validation";

type Ctx = RouteContext<"/api/lessons/[id]">;

/** Replace the content of a saved lesson (after a revision in /app). */
export async function PUT(request: Request, ctx: Ctx) {
  const userId = await apiUserId();
  if (!userId) return unauthorized();
  const { id } = await ctx.params;
  const parsed = lessonPayloadSchema.safeParse(await readJson(request));
  if (!parsed.success) return json({ error: "That does not look like a Structura lesson." }, 400);
  try {
    return (await updateLessonContent(userId, id, parsed.data as unknown as Lesson)) ? json({ ok: true }) : notFound();
  } catch (err) {
    return dbDown(err);
  }
}

/** Rename or pin/unpin. */
export async function PATCH(request: Request, ctx: Ctx) {
  const userId = await apiUserId();
  if (!userId) return unauthorized();
  const { id } = await ctx.params;
  const parsed = lessonPatchSchema.safeParse(await readJson(request));
  if (!parsed.success) return json({ error: parsed.error.issues[0]?.message ?? "Invalid update." }, 400);
  try {
    return (await patchLesson(userId, id, parsed.data)) ? json({ ok: true }) : notFound();
  } catch (err) {
    return dbDown(err);
  }
}

export async function DELETE(_request: Request, ctx: Ctx) {
  const userId = await apiUserId();
  if (!userId) return unauthorized();
  const { id } = await ctx.params;
  try {
    return (await deleteLesson(userId, id)) ? json({ ok: true }) : notFound();
  } catch (err) {
    return dbDown(err);
  }
}
