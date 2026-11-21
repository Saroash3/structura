import Link from "next/link";
import { Logo } from "@/components/logo";

const COLUMNS: { title: string; links: { label: string; href: string }[] }[] = [
  {
    title: "Product",
    links: [
      { label: "How it works", href: "/#how" },
      { label: "Topics", href: "/#topics" },
      { label: "Start a lesson", href: "/app" },
    ],
  },
  {
    title: "Account",
    links: [
      { label: "Log in", href: "/login" },
      { label: "Sign up", href: "/signup" },
      { label: "Dashboard", href: "/dashboard" },
    ],
  },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-border">
      <div className="container-page grid gap-10 py-14 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1.4fr]">
        <div className="flex flex-col gap-4">
          <Logo />
          <p className="max-w-xs text-sm leading-relaxed text-muted">
            Watch data structures move, step by step. Gemini plans, Python verifies, Piper narrates locally.
          </p>
        </div>
        {COLUMNS.map((col) => (
          <nav key={col.title} aria-label={col.title}>
            <h2 className="mb-4 text-sm font-semibold text-text">{col.title}</h2>
            <ul className="flex flex-col gap-2.5 text-sm">
              {col.links.map((l) => (
                <li key={l.href}>
                  <Link href={l.href} className="text-muted transition-colors hover:text-text">{l.label}</Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}
        <div>
          <h2 className="mb-4 text-sm font-semibold text-text">Project</h2>
          <p className="text-sm text-muted">NLP course project</p>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
            <dt className="text-text">Saroash Waseem</dt><dd className="font-mono text-muted">22i-2609</dd>
            <dt className="text-text">Agha Ahsan</dt><dd className="font-mono text-muted">21i-1117</dd>
          </dl>
        </div>
      </div>
      <div className="border-t border-border">
        <p className="container-page py-5 text-xs text-muted">
          Everything except the Gemini call runs locally. Every narrated fact is checked against a real data structure.
        </p>
      </div>
    </footer>
  );
}
