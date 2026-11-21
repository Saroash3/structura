import Link from "next/link";
import { ArrowUpRight, Sparkles } from "lucide-react";
import { Marquee } from "@/components/ui/marquee";
import { OffscreenPause } from "@/components/landing/offscreen-pause";
import { EXAMPLE_PROMPTS } from "@/lib/facts";

const href = (p: string) => `/app?topic=${encodeURIComponent(p)}`;
const half = Math.ceil(EXAMPLE_PROMPTS.length / 2);

function Pill({ prompt }: { prompt: string }) {
  return (
    <Link href={href(prompt)} tabIndex={-1}
      className="group inline-flex items-center gap-2 rounded-full border border-border bg-surface px-4 py-2.5 text-sm whitespace-nowrap text-text transition-colors hover:border-accent2 hover:text-accent2">
      <Sparkles className="size-3.5 text-accent transition-transform group-hover:rotate-12" aria-hidden />
      {prompt}
      <ArrowUpRight className="size-3.5 text-muted transition-colors group-hover:text-accent2" aria-hidden />
    </Link>
  );
}

/**
 * Scrolling example prompts. The animated rows repeat their children, so they are hidden from
 * assistive tech and the tab order; a single accessible list (visible on keyboard focus) mirrors them.
 */
export function PromptMarquee() {
  return (
    <section aria-labelledby="prompts-title" className="py-14 lg:py-16">
      <h2 id="prompts-title" className="container-page mb-6 text-center text-sm text-muted">
        Try asking. Click a prompt to start a lesson with it.
      </h2>
      <ul className="container-page sr-only flex-wrap justify-center gap-2 focus-within:not-sr-only focus-within:mb-6 focus-within:flex">
        {EXAMPLE_PROMPTS.map((p) => (
          <li key={p}>
            <Link href={href(p)} className="inline-flex rounded-full border border-border bg-surface px-4 py-2 text-sm">{p}</Link>
          </li>
        ))}
      </ul>
      <OffscreenPause className="relative [mask-image:linear-gradient(to_right,transparent,black_12%,black_88%,transparent)]">
        <Marquee pauseOnHover className="[--duration:45s] [--gap:0.75rem]">
          {EXAMPLE_PROMPTS.slice(0, half).map((p) => <Pill key={p} prompt={p} />)}
        </Marquee>
        <Marquee pauseOnHover reverse className="[--duration:50s] [--gap:0.75rem]">
          {EXAMPLE_PROMPTS.slice(half).map((p) => <Pill key={p} prompt={p} />)}
        </Marquee>
      </OffscreenPause>
    </section>
  );
}
