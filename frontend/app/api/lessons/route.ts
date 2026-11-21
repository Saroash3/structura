import { apiUserId, dbDown, json, readJson, unauthorized } from "@/lib/api-auth";
import { createLesson } from "@/lib/data";
import type { Lesson } from "@/lib/types";
import { lessonPayloadSchema } from "@/lib/validation";

/** Save a freshly generated (already verified) lesson for the signed-in user. */
export async function POST(request: Request) {
  const userId = await apiUserId();
  if (!userId) return unauthorized();
  const parsed = lessonPayloadSchema.safeParse(await readJson(request));
  if (!parsed.success) return json({ error: "That does not look like a Structura lesson." }, 400);
  try {
    const id = await createLesson(userId, parsed.data as unknown as Lesson);
    return json({ id }, 201);
  } catch (err) {
    return dbDown(err);
  }
}
