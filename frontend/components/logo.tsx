import Link from "next/link";

/** `compact`: hide the wordmark on small screens (the link keeps its accessible name). */
export function Logo({ href = "/", compact = false }: { href?: string; compact?: boolean }) {
  return (
    <Link href={href} className="flex items-center gap-2.5 rounded-lg" aria-label="Structura home">
      <span className="flex gap-1" aria-hidden>
        <span className="size-2.5 rounded-[3px] bg-accent" />
        <span className="size-2.5 rounded-[3px] bg-accent2" />
        <span className="size-2.5 rounded-[3px] bg-text" />
      </span>
      <span className={`font-heading text-lg font-semibold tracking-tight ${compact ? "hidden sm:inline" : ""}`}>Structura</span>
    </Link>
  );
}
