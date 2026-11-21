"use client";

import { useState } from "react";
import { signOut } from "next-auth/react";
import { Loader2, LogOut } from "lucide-react";

export function SignOutButton() {
  const [busy, setBusy] = useState(false);
  return (
    <button type="button" disabled={busy} onClick={() => { setBusy(true); void signOut({ redirectTo: "/" }); }}
      className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-muted hover:text-text disabled:opacity-60">
      {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <LogOut className="size-4" aria-hidden />}
      <span className="sr-only sm:not-sr-only">Log out</span>
    </button>
  );
}
