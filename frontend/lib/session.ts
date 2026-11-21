import "server-only";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { auth } from "@/auth";

export type SessionUser = { id: string; name: string; email: string };

/**
 * Data Access Layer entry point: returns the signed-in user or redirects to /login.
 * Every database query for user data must use the id returned here.
 * Reads cookies, so call it inside a <Suspense> boundary.
 */
export async function requireUser(): Promise<SessionUser> {
  await connection(); // per-request: Auth.js uses random values before it reads cookies
  const session = await auth();
  const user = session?.user;
  if (!user?.id) redirect("/login");
  return { id: user.id, name: user.name ?? "", email: user.email ?? "" };
}
