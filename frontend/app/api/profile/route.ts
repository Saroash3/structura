import bcrypt from "bcryptjs";
import { z } from "zod";
import { unstable_update } from "@/auth";
import { apiUserId, dbDown, json, readJson, unauthorized } from "@/lib/api-auth";
import { deleteAccount, getPasswordHash, updateProfile } from "@/lib/data";
import { isRateLimited, recordFailure } from "@/lib/rate-limit";
import { fieldErrors, profileSchema } from "@/lib/validation";

/** Update display name and default learner level. */
export async function PATCH(request: Request) {
  const userId = await apiUserId();
  if (!userId) return unauthorized();
  const parsed = profileSchema.safeParse(await readJson(request));
  if (!parsed.success) return json({ error: "Please fix the highlighted fields.", fields: fieldErrors(parsed.error) }, 400);
  try {
    await updateProfile(userId, parsed.data);
  } catch (err) {
    return dbDown(err);
  }
  await unstable_update({ user: { name: parsed.data.name } }); // refresh the name stored in the session cookie
  return json({ ok: true });
}

/** Delete the account and everything it owns. Requires the current password. */
export async function DELETE(request: Request) {
  const userId = await apiUserId();
  if (!userId) return unauthorized();
  const parsed = z.object({ password: z.string().min(1).max(128) }).safeParse(await readJson(request));
  if (!parsed.success) return json({ error: "Enter your password to confirm." }, 400);
  const key = `delete:${userId}`;
  if (isRateLimited(key)) return json({ error: "Too many attempts. Wait 15 minutes and try again." }, 429);
  try {
    const hash = await getPasswordHash(userId);
    if (!hash || !(await bcrypt.compare(parsed.data.password, hash))) {
      recordFailure(key);
      return json({ error: "That password is not correct." }, 403);
    }
    await deleteAccount(userId);
    return json({ ok: true });
  } catch (err) {
    return dbDown(err);
  }
}
