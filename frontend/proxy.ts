import NextAuth from "next-auth";
import { authConfig } from "./auth.config";

// Route protection: signed-out users hitting a protected page are sent to /login?callbackUrl=...
// Pages also re-check the session on the server (see lib/session.ts), so this is not the only guard.
const { auth } = NextAuth(authConfig);

export default auth;

export const config = {
  matcher: ["/app/:path*", "/dashboard/:path*", "/lesson/:path*", "/profile/:path*", "/login", "/signup"],
};
