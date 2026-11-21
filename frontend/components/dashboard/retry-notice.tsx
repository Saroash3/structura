"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Loader2 } from "lucide-react";

const DELAYS = [1000, 3000, 8000]; // ms before each automatic retry

/**
 * Shown when the dashboard could not read the database. Instead of asking the user to refresh, it re-fetches the
 * server data by itself a few times (after a network blip a refresh usually works at once). When a retry succeeds
 * the server sends the real dashboard and this component unmounts; after the last retry it gives up honestly.
 */
export function RetryNotice() {
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);
  const gaveUp = attempt >= DELAYS.length;

  useEffect(() => {
    if (gaveUp) return;
    const t = setTimeout(() => {
      router.refresh();
      setAttempt((a) => a + 1);
    }, DELAYS[attempt]);
    return () => clearTimeout(t);
  }, [attempt, gaveUp, router]);

  if (!gaveUp) {
    return (
      <div role="status" className="flex items-center gap-3 rounded-2xl border border-border bg-surface p-5 text-muted">
        <Loader2 className="size-5 shrink-0 animate-spin text-accent" aria-hidden />
        <p>Reconnecting to the database&hellip;</p>
      </div>
    );
  }
  return (
    <div role="alert" className="flex items-start gap-3 rounded-2xl border border-destructive/60 bg-destructive/10 p-5">
      <AlertCircle className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
      <div>
        <p className="font-semibold">Could not load your dashboard</p>
        <p className="text-sm text-muted">The database is still unreachable. Check your internet connection, then refresh the page.</p>
      </div>
    </div>
  );
}
