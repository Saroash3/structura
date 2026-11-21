import { apiUserId, dbDown, json, readJson, unauthorized } from "@/lib/api-auth";
import { createQuizResult } from "@/lib/data";
import { quizResultSchema } from "@/lib/validation";

/** Save a finished quiz (score out of total) for the signed-in user. */
export async function POST(request: Request) {
  const userId = await apiUserId();
  if (!userId) return unauthorized();
  const parsed = quizResultSchema.safeParse(await readJson(request));
  if (!parsed.success) return json({ error: parsed.error.issues[0]?.message ?? "Invalid quiz result." }, 400);
  try {
    return json({ id: await createQuizResult(userId, parsed.data) }, 201);
  } catch (err) {
    return dbDown(err);
  }
}
