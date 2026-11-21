import { Suspense } from "react";
import { BadgeCheck } from "lucide-react";
import { Logo } from "@/components/logo";
import { AuthForm } from "@/components/auth-form";
import { DotPattern } from "@/components/ui/dot-pattern";

// The animated panel is decorative and desktop-only, so it loads in its own chunk.
import { LiveDemo } from "@/components/landing/lazy-sections";

const COPY = {
  login: { title: "Welcome back", subtitle: "Log in to open your lessons and quiz history." },
  signup: { title: "Create your account", subtitle: "Save lessons, track quiz scores, and pick up where you left off." },
};

export function AuthShell({ mode }: { mode: "login" | "signup" }) {
  const { title, subtitle } = COPY[mode];
  return (
    <main className="grid min-h-screen lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      {/* form */}
      <div className="flex flex-col px-4 py-6 sm:px-10">
        <Logo />
        <div className="flex flex-1 items-center justify-center py-12">
          <section aria-labelledby="auth-title" className="w-full max-w-sm">
            <h1 id="auth-title" className="text-3xl font-semibold tracking-tight">{title}</h1>
            <p className="mt-2 mb-8 text-muted">{subtitle}</p>
            <Suspense fallback={<div className="h-80 animate-pulse rounded-xl bg-surface" aria-hidden />}>
              <AuthForm mode={mode} />
            </Suspense>
          </section>
        </div>
        <p className="text-xs text-muted">Passwords are hashed with bcrypt. Sessions use signed cookies.</p>
      </div>

      {/* animated panel */}
      <aside aria-hidden className="relative isolate hidden overflow-hidden border-l border-border bg-stage lg:flex lg:flex-col lg:justify-center lg:px-12 xl:px-16">
        <DotPattern width={22} height={22} cr={1} className="-z-10 text-border [mask-image:radial-gradient(ellipse_at_center,black_30%,transparent_75%)]" />
        <div className="absolute top-1/3 left-1/2 -z-10 size-[30rem] -translate-x-1/2 rounded-full bg-accent/10 blur-3xl" />
        <div className="mx-auto w-full max-w-lg">
          <p className="eyebrow mb-4"><span className="h-px w-6 bg-accent" />Live lesson</p>
          <h2 className="text-title mb-8">Every frame is a true state.</h2>
          <LiveDemo />
          <p className="mt-6 inline-flex items-center gap-2 text-sm text-muted">
            <BadgeCheck className="size-4 text-accent2" /> Narration checked against a real queue before you hear it.
          </p>
        </div>
      </aside>
    </main>
  );
}
