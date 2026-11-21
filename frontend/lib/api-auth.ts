import "server-only";
import { NextResponse } from "next/server";
import { auth } from "@/auth";

/** For Route Handlers: the signed-in user's id, or null (respond with `unauthorized()`). */
export async function apiUserId(): Promise<string | null> {
  const session = await auth();
  return session?.user?.id ?? null;
}

export const json = (data: unknown, status = 200) => NextResponse.json(data, { status });
export const unauthorized = () => json({ error: "Please log in again." }, 401);
export const notFound = () => json({ error: "Not found." }, 404);
export const dbDown = (err: unknown) => {
  console.error("[db]", err instanceof Error ? err.message : err);
  return json({ error: "The database is unavailable. Try again in a moment." }, 503);
};

const MAX_BODY = 3_000_000; // ~3 MB: a full lesson snapshot is far smaller

/** Reads a JSON body with a size cap. Returns undefined on bad JSON or oversized bodies. */
export async function readJson(request: Request): Promise<unknown> {
  const text = await request.text().catch(() => "");
  if (!text || text.length > MAX_BODY) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}
