import Link from "next/link";
import { connection } from "next/server";
import { auth } from "@/auth";
import { cn } from "@/lib/utils";

type Variant = "bar" | "sheet";

const linkCls = (v: Variant) =>
  v === "bar"
    ? "rounded-lg px-3 py-2 text-sm text-muted transition-colors hover:text-text"
    : "flex h-11 items-center rounded-lg px-3 text-base text-text hover:bg-surface";
const ctaCls = (v: Variant) =>
  cn(
    "inline-flex items-center justify-center rounded-lg bg-accent font-semibold text-on-accent transition-[transform,background-color] hover:bg-accent/90 active:scale-[0.97]",
    v === "bar" ? "h-9 px-4 text-sm" : "h-11 w-full px-4 text-base",
  );

/** Shown while the session loads, and to signed-out visitors. */
export function GuestActions({ variant = "bar" }: { variant?: Variant }) {
  return (
    <>
      <Link href="/login" className={linkCls(variant)}>Log in</Link>
      <Link href="/signup" className={ctaCls(variant)}>Sign up</Link>
    </>
  );
}

/** Reads the session (render inside <Suspense>): signed-in visitors get shortcuts instead. */
export async function NavActions({ variant = "bar" }: { variant?: Variant }) {
  await connection(); // per-request: Auth.js uses random values before it reads cookies
  const session = await auth();
  if (!session?.user) return <GuestActions variant={variant} />;
  return (
    <>
      <Link href="/dashboard" className={linkCls(variant)}>Dashboard</Link>
      <Link href="/app" className={ctaCls(variant)}>New lesson</Link>
    </>
  );
}
