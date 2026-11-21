import { Suspense } from "react";
import type { Metadata } from "next";
import { AlertCircle } from "lucide-react";
import { AppNav } from "@/components/app-nav";
import { ProfileForms } from "@/components/profile-forms";
import { Skeleton } from "@/components/ui/skeleton";
import { getProfile } from "@/lib/data";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = { title: "Profile | Structura" };

async function ProfileContent() {
  const user = await requireUser();
  const profile = await getProfile(user.id).catch(() => undefined);
  if (!profile) {
    return (
      <div role="alert" className="flex items-start gap-3 rounded-2xl border border-destructive/60 bg-destructive/10 p-5">
        <AlertCircle className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
        <p>Could not load your profile. The database may be unavailable; refresh in a moment.</p>
      </div>
    );
  }
  return <ProfileForms name={profile.name} email={profile.email} level={profile.level} />;
}

export default function ProfilePage() {
  return (
    <>
      <AppNav current="profile" />
      <main className="container-page max-w-2xl py-12 lg:py-16">
        <div className="mb-10">
          <p className="eyebrow mb-3"><span className="h-px w-6 bg-accent" aria-hidden />Account</p>
          <h1 className="text-title">Profile and settings</h1>
        </div>
        <Suspense fallback={<div className="flex flex-col gap-6" role="status" aria-label="Loading profile">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-52 rounded-2xl bg-surface" />)}</div>}>
          <ProfileContent />
        </Suspense>
      </main>
    </>
  );
}
