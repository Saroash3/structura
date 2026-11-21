"use client";

import { useEffect, useState } from "react";
import { motion, useMotionValueEvent, useScroll } from "motion/react";
import { Menu } from "lucide-react";
import { Logo } from "@/components/logo";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

const SECTIONS = [
  { id: "how", label: "How it works" },
  { id: "topics", label: "Topics" },
];

/** Highlights the section currently in the middle of the viewport. */
function useActiveSection(ids: string[]) {
  const [active, setActive] = useState<string | null>(null);
  useEffect(() => {
    const els = ids.map((id) => document.getElementById(id)).filter((el): el is HTMLElement => el !== null);
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) if (e.isIntersecting) setActive(e.target.id);
      },
      { rootMargin: "-45% 0px -50% 0px" },
    );
    els.forEach((el) => io.observe(el));
    const onTop = () => window.scrollY < 200 && setActive(null);
    window.addEventListener("scroll", onTop, { passive: true });
    return () => {
      io.disconnect();
      window.removeEventListener("scroll", onTop);
    };
  }, [ids]);
  return active;
}

const SECTION_IDS = SECTIONS.map((s) => s.id);

/**
 * Sticky landing nav. `actions` / `mobileActions` are server-rendered (they read the session),
 * passed in as slots so this client component never touches auth.
 */
export function SiteNav({ actions, mobileActions }: { actions: React.ReactNode; mobileActions: React.ReactNode }) {
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const active = useActiveSection(SECTION_IDS);
  useMotionValueEvent(scrollY, "change", (y) => setScrolled(y > 12));

  return (
    <header
      className={cn(
        "sticky top-0 z-50 border-b transition-[background-color,border-color,backdrop-filter] duration-300",
        scrolled ? "border-border/70 bg-background/90 backdrop-blur-md" : "border-transparent bg-transparent",
      )}>
      <nav aria-label="Main" className="container-page flex h-16 items-center justify-between gap-4">
        <Logo />
        <ul className="hidden items-center gap-1 md:flex">
          {SECTIONS.map((s) => (
            <li key={s.id}>
              <a href={`#${s.id}`} aria-current={active === s.id ? "true" : undefined}
                className={cn("relative rounded-lg px-3 py-2 text-sm transition-colors", active === s.id ? "text-text" : "text-muted hover:text-text")}>
                {s.label}
                {active === s.id && (
                  <motion.span layoutId="nav-active" className="absolute inset-x-3 -bottom-0.5 h-0.5 rounded-full bg-accent"
                    transition={{ type: "spring", stiffness: 380, damping: 32 }} />
                )}
              </a>
            </li>
          ))}
        </ul>
        <div className="hidden items-center gap-1 md:flex">{actions}</div>

        <Sheet open={open} onOpenChange={setOpen}>
          <SheetTrigger aria-label="Open menu"
            className="grid size-10 place-items-center rounded-lg border border-border text-text transition-transform active:scale-95 md:hidden">
            <Menu className="size-5" aria-hidden />
          </SheetTrigger>
          <SheetContent side="right" className="border-border bg-background">
            <SheetHeader>
              <SheetTitle className="font-heading">Menu</SheetTitle>
            </SheetHeader>
            {/* closing on click lets anchor links scroll the page behind the sheet */}
            <div className="flex flex-col gap-1 px-4" onClick={(e) => (e.target as HTMLElement).closest("a") && setOpen(false)}>
              {SECTIONS.map((s) => (
                <a key={s.id} href={`#${s.id}`} className="flex h-11 items-center rounded-lg px-3 text-base text-text hover:bg-surface">
                  {s.label}
                </a>
              ))}
              <div className="my-3 h-px bg-border" />
              <div className="flex flex-col gap-2">{mobileActions}</div>
            </div>
          </SheetContent>
        </Sheet>
      </nav>
    </header>
  );
}
