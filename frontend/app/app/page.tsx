import { Suspense } from "react";
import type { Metadata } from "next";
import { Generator } from "@/components/generator";
import { getProfile } from "@/lib/data";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = { title: "New lesson | Structura" };

/** Reads the user's default learner level; the generator still works if the database is down. */
async function GeneratorForUser() {
  const user = await requireUser();
  const level = await getProfile(user.id).then((p) => p?.level ?? "beginner").catch(() => "beginner" as const);
  return <Generator initialLevel={level} />;
}

// Protected by proxy.ts and requireUser. The generator reads ?topic= and the session, so it sits in Suspense.
export default function AppPage() {
  return (
    <Suspense fallback={<div className="min-h-screen" aria-busy="true" />}>
      <GeneratorForUser />
    </Suspense>
  );
}
