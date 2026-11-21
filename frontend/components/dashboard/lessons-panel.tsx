"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { Loader2, Pencil, Pin, PinOff, Play, Search, Trash2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { deleteLesson, patchLesson } from "@/lib/account-api";
import type { LessonSummary } from "@/lib/data";
import { structureLabel } from "@/lib/structure-labels";
import { useMounted } from "@/lib/use-mounted";
import { cn } from "@/lib/utils";

const spring = { type: "spring" as const, stiffness: 380, damping: 32 };
const fmtDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
const sortLessons = (ls: LessonSummary[]) =>
  [...ls].sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.updatedAt.localeCompare(a.updatedAt));

function IconButton({ label, onClick, children, pressed }: { label: string; onClick: () => void; children: React.ReactNode; pressed?: boolean }) {
  return (
    <button type="button" onClick={onClick} aria-label={label} aria-pressed={pressed} title={label}
      className="grid size-9 place-items-center rounded-lg text-muted transition-colors hover:bg-background hover:text-text">
      {children}
    </button>
  );
}

export function LessonsPanel({ initial }: { initial: LessonSummary[] }) {
  const router = useRouter();
  const mounted = useMounted(); // dates are locale-dependent: render them on the client only
  const [lessons, setLessons] = useState(() => sortLessons(initial));
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);
  const [renaming, setRenaming] = useState<LessonSummary | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [deleting, setDeleting] = useState<LessonSummary | null>(null);
  const [busy, setBusy] = useState(false);

  const structures = useMemo(() => [...new Set(lessons.map((l) => l.structure))], [lessons]);
  const visible = lessons.filter((l) =>
    (filter === "all" || l.structure === filter) &&
    (!query.trim() || `${l.title} ${l.topic}`.toLowerCase().includes(query.trim().toLowerCase())));

  /** Optimistic update with rollback if the server refuses. */
  async function mutate(next: LessonSummary[], action: () => Promise<unknown>) {
    const before = lessons;
    setLessons(sortLessons(next));
    setError(null);
    try {
      await action();
      router.refresh(); // keep the stat cards in sync
    } catch (e) {
      setLessons(before);
      setError(e instanceof Error ? e.message : "Something went wrong.");
    }
  }

  const togglePin = (l: LessonSummary) =>
    mutate(lessons.map((x) => (x.id === l.id ? { ...x, pinned: !x.pinned } : x)), () => patchLesson(l.id, { pinned: !l.pinned }));

  async function confirmRename(e: React.FormEvent) {
    e.preventDefault();
    if (!renaming) return;
    const title = newTitle.trim();
    if (!title || title.length > 120) return setError("Title must be 1 to 120 characters.");
    setBusy(true);
    await mutate(lessons.map((x) => (x.id === renaming.id ? { ...x, title } : x)), () => patchLesson(renaming.id, { title }));
    setBusy(false);
    setRenaming(null);
  }

  async function confirmDelete() {
    if (!deleting) return;
    setBusy(true);
    await mutate(lessons.filter((x) => x.id !== deleting.id), () => deleteLesson(deleting.id));
    setBusy(false);
    setDeleting(null);
  }

  return (
    <section aria-labelledby="saved-title" className="flex flex-col gap-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <h2 id="saved-title" className="text-2xl font-semibold">Saved lessons <span className="text-base font-normal text-muted">({lessons.length})</span></h2>
        <div className="relative w-full lg:w-72">
          <label htmlFor="lesson-search" className="sr-only">Search lessons</label>
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" aria-hidden />
          <Input id="lesson-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search lessons"
            className="h-10 rounded-xl bg-surface pl-9" />
        </div>
      </div>

      <div role="group" aria-label="Filter by topic" className="flex flex-wrap gap-2">
        {["all", ...structures].map((s) => (
          <button key={s} type="button" onClick={() => setFilter(s)} aria-pressed={filter === s}
            className={cn("rounded-full border px-3.5 py-1.5 text-sm transition-colors",
              filter === s ? "border-accent2 bg-accent2/15 text-text" : "border-border text-muted hover:text-text")}>
            {s === "all" ? "All topics" : structureLabel(s)}
          </button>
        ))}
      </div>

      {error && <p role="alert" className="rounded-xl border border-destructive/60 bg-destructive/10 px-4 py-3 text-sm">{error}</p>}

      <motion.ul layout className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <AnimatePresence mode="popLayout" initial={false}>
          {visible.map((l) => (
            <motion.li key={l.id} layout initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.94, transition: { duration: 0.2 } }} transition={spring}
              className="group flex flex-col rounded-2xl border border-border bg-surface p-5 transition-[border-color,transform] hover:-translate-y-0.5 hover:border-accent/50">
              <div className="mb-3 flex items-center justify-between gap-2">
                <span className="rounded-full border border-border px-2.5 py-0.5 text-xs text-muted">{structureLabel(l.structure)}</span>
                {l.pinned && <span className="inline-flex items-center gap-1 text-xs text-accent"><Pin className="size-3" aria-hidden />Pinned</span>}
              </div>
              <h3 className="line-clamp-2 text-lg font-semibold">{l.title}</h3>
              <p className="mt-1 text-sm text-muted">{l.scenes} steps &middot; {l.duration}s &middot; {l.level}{mounted && <> &middot; {fmtDate(l.updatedAt)}</>}</p>
              <div className="mt-5 flex items-center justify-between gap-2">
                <Link href={`/lesson/${l.id}`}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-accent px-3.5 text-sm font-semibold text-on-accent transition-transform hover:bg-accent/90 active:scale-[0.97]">
                  <Play className="size-3.5" aria-hidden /> Open<span className="sr-only">: {l.title}</span>
                </Link>
                <div className="flex items-center">
                  <IconButton label={l.pinned ? `Unpin ${l.title}` : `Pin ${l.title}`} pressed={l.pinned} onClick={() => void togglePin(l)}>
                    {l.pinned ? <PinOff className="size-4" /> : <Pin className="size-4" />}
                  </IconButton>
                  <IconButton label={`Rename ${l.title}`} onClick={() => { setRenaming(l); setNewTitle(l.title); }}>
                    <Pencil className="size-4" />
                  </IconButton>
                  <IconButton label={`Delete ${l.title}`} onClick={() => setDeleting(l)}>
                    <Trash2 className="size-4" />
                  </IconButton>
                </div>
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
      </motion.ul>
      {visible.length === 0 && lessons.length > 0 && (
        <p className="rounded-2xl border border-dashed border-border px-6 py-10 text-center text-muted">No lessons match your search.</p>
      )}

      {/* rename */}
      <Dialog open={renaming !== null} onOpenChange={(o) => !o && setRenaming(null)}>
        <DialogContent className="border-border bg-surface sm:max-w-md">
          <form onSubmit={confirmRename} className="flex flex-col gap-4">
            <DialogHeader>
              <DialogTitle>Rename lesson</DialogTitle>
              <DialogDescription>Give this lesson a name you will recognise later.</DialogDescription>
            </DialogHeader>
            <label htmlFor="rename-input" className="sr-only">Lesson title</label>
            <Input id="rename-input" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} maxLength={120} autoFocus className="h-11 bg-background" />
            <DialogFooter>
              <button type="button" onClick={() => setRenaming(null)} className="h-10 rounded-lg px-4 text-sm text-muted hover:text-text">Cancel</button>
              <button type="submit" disabled={busy || !newTitle.trim()}
                className="inline-flex h-10 items-center gap-2 rounded-lg bg-accent px-4 text-sm font-semibold text-on-accent disabled:opacity-50">
                {busy && <Loader2 className="size-4 animate-spin" aria-hidden />} Save
              </button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* delete */}
      <Dialog open={deleting !== null} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent className="border-border bg-surface sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete this lesson?</DialogTitle>
            <DialogDescription>
              &ldquo;{deleting?.title}&rdquo; will be removed from your dashboard. Your quiz history stays. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <button type="button" onClick={() => setDeleting(null)} className="h-10 rounded-lg px-4 text-sm text-muted hover:text-text">Cancel</button>
            <button type="button" onClick={() => void confirmDelete()} disabled={busy}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-destructive px-4 text-sm font-semibold text-on-accent disabled:opacity-50">
              {busy && <Loader2 className="size-4 animate-spin" aria-hidden />} Delete lesson
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
