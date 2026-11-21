import Link from "next/link";
import { Logo } from "@/components/logo";
import { SignOutButton } from "@/components/sign-out-button";
import { cn } from "@/lib/utils";

const LINKS = [
  { key: "app", label: "New lesson", href: "/app" },
  { key: "dashboard", label: "Dashboard", href: "/dashboard" },
  { key: "profile", label: "Profile", href: "/profile" },
] as const;

/** Navigation for signed-in pages: sticky, blurred, active link underlined in accent. */
export function AppNav({ current }: { current?: (typeof LINKS)[number]["key"] }) {
  return (
    <header className="sticky top-0 z-50 border-b border-border/70 bg-background/90 backdrop-blur-md">
      <nav aria-label="Main" className="container-page flex h-16 items-center justify-between gap-3">
        <Logo href="/dashboard" compact />
        <ul className="flex items-center gap-0.5 text-sm sm:gap-1">
          {LINKS.map((l) => (
            <li key={l.key}>
              <Link href={l.href} aria-current={current === l.key ? "page" : undefined}
                className={cn("relative rounded-lg px-2 py-2 transition-colors sm:px-3", current === l.key ? "text-text" : "text-muted hover:text-text")}>
                {l.label}
                {current === l.key && <span className="absolute inset-x-2 -bottom-0.5 h-0.5 rounded-full bg-accent sm:inset-x-3" aria-hidden />}
              </Link>
            </li>
          ))}
          <li><SignOutButton /></li>
        </ul>
      </nav>
    </header>
  );
}
