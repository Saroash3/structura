import bcrypt from "bcryptjs";
import { apiUserId, dbDown, json, readJson, unauthorized } from "@/lib/api-auth";
import { getPasswordHash, updateProfile } from "@/lib/data";
import { clearFailures, isRateLimited, recordFailure } from "@/lib/rate-limit";
import { fieldErrors, passwordChangeSchema } from "@/lib/validation";

/** Change password: the current password must be correct (rate-limited like login). */
export async function POST(request: Request) {
  const userId = await apiUserId();
  if (!userId) return unauthorized();
  const parsed = passwordChangeSchema.safeParse(await readJson(request));
  if (!parsed.success) return json({ error: "Please fix the highlighted fields.", fields: fieldErrors(parsed.error) }, 400);
  const key = `password:${userId}`;
  if (isRateLimited(key)) return json({ error: "Too many attempts. Wait 15 minutes and try again." }, 429);
  try {
    const hash = await getPasswordHash(userId);
    if (!hash || !(await bcrypt.compare(parsed.data.currentPassword, hash))) {
      recordFailure(key);
      return json({ error: "Your current password is not correct.", fields: { currentPassword: "Not correct." } }, 403);
    }
    if (await bcrypt.compare(parsed.data.newPassword, hash)) {
      return json({ error: "Choose a password you have not used here before.", fields: { newPassword: "Same as your current password." } }, 400);
    }
    clearFailures(key);
    await updateProfile(userId, { passwordHash: await bcrypt.hash(parsed.data.newPassword, 12) });
    return json({ ok: true });
  } catch (err) {
    return dbDown(err);
  }
}
