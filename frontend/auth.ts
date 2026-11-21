import NextAuth, { CredentialsSignin } from "next-auth";
import Credentials from "next-auth/providers/credentials";
import bcrypt from "bcryptjs";
import { authConfig } from "./auth.config";
import { connectDB } from "@/lib/db";
import { User } from "@/lib/models";
import { clearFailures, isRateLimited, recordFailure } from "@/lib/rate-limit";
import { loginSchema } from "@/lib/validation";

class RateLimited extends CredentialsSignin {
  code = "rate_limited";
}
class DatabaseUnavailable extends CredentialsSignin {
  code = "db_unavailable";
}

// A real bcrypt hash of a random string: comparing against it keeps timing similar for unknown emails.
const DUMMY_HASH = "$2b$12$DYhugSwOBTeQs0XzSEBKjukg4oePC410LQsW4aCdfKJBOIrhtcmTa";

export const { handlers, auth, signIn, signOut, unstable_update } = NextAuth({
  ...authConfig,
  providers: [
    Credentials({
      credentials: { email: { label: "Email" }, password: { label: "Password", type: "password" } },
      async authorize(raw, request) {
        const parsed = loginSchema.safeParse(raw);
        if (!parsed.success) return null;
        const { email, password } = parsed.data;

        const ip = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "local";
        const key = `${ip}:${email}`;
        if (isRateLimited(key)) throw new RateLimited();

        try {
          await connectDB();
        } catch {
          throw new DatabaseUnavailable();
        }
        const user = await User.findOne({ email }).lean();
        const ok = await bcrypt.compare(password, user?.passwordHash ?? DUMMY_HASH);
        if (!user || !ok) {
          recordFailure(key);
          return null;
        }
        clearFailures(key);
        return { id: String(user._id), name: user.name, email: user.email };
      },
    }),
  ],
});
