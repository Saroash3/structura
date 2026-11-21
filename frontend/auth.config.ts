import type { NextAuthConfig } from "next-auth";

/** Routes that need a signed-in user. */
export const PROTECTED_PREFIXES = ["/app", "/dashboard", "/lesson", "/profile"];
const AUTH_PAGES = ["/login", "/signup"];

const matches = (path: string, prefixes: string[]) => prefixes.some((p) => path === p || path.startsWith(`${p}/`));

/**
 * Edge-safe part of the auth config (no database imports). Used by proxy.ts for route protection
 * and extended with the Credentials provider in auth.ts.
 */
export const authConfig = {
  pages: { signIn: "/login" },
  session: { strategy: "jwt", maxAge: 30 * 24 * 60 * 60 },
  trustHost: true, // local app; the Host header is trusted
  providers: [],
  callbacks: {
    authorized({ auth, request: { nextUrl } }) {
      const signedIn = Boolean(auth?.user);
      if (matches(nextUrl.pathname, PROTECTED_PREFIXES)) return signedIn; // false -> /login?callbackUrl=...
      if (signedIn && matches(nextUrl.pathname, AUTH_PAGES)) {
        return Response.redirect(new URL("/dashboard", nextUrl));
      }
      return true;
    },
    jwt({ token, user, trigger, session }) {
      if (user?.id) token.uid = user.id;
      // profile rename: the /api/profile route calls unstable_update({ user: { name } })
      const newName: unknown = trigger === "update" ? (session as { user?: { name?: unknown } } | undefined)?.user?.name : undefined;
      if (typeof newName === "string" && newName.trim()) token.name = newName.trim();
      return token;
    },
    session({ session, token }) {
      if (typeof token.uid === "string") session.user.id = token.uid;
      return session;
    },
  },
} satisfies NextAuthConfig;
