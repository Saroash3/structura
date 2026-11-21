"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { signOut } from "next-auth/react";
import { AlertCircle, Check, Loader2, Trash2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { fieldErrors, passwordChangeSchema, profileSchema } from "@/lib/validation";
import { cn } from "@/lib/utils";

type Level = "beginner" | "intermediate";
type Status = { kind: "idle" | "saving" } | { kind: "ok"; text: string } | { kind: "error"; text: string };

async function send(path: string, method: string, body: unknown): Promise<{ ok: boolean; error?: string; fields?: Record<string, string> }> {
  try {
    const res = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = (await res.json().catch(() => ({}))) as { error?: string; fields?: Record<string, string> };
    return { ok: res.ok, ...data };
  } catch {
    return { ok: false, error: "Could not reach the server. Check your connection." };
  }
}

function Card({ title, description, children, danger }: { title: string; description: string; children: React.ReactNode; danger?: boolean }) {
  return (
    <section className={cn("rounded-2xl border bg-surface p-6", danger ? "border-destructive/50" : "border-border")}>
      <h2 className={cn("text-lg font-semibold", danger && "text-destructive")}>{title}</h2>
      <p className="mt-1 mb-6 text-sm text-muted">{description}</p>
      {children}
    </section>
  );
}

function Field({ id, label, error, ...props }: React.ComponentProps<typeof Input> & { id: string; label: string; error?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">{label}</label>
      <Input id={id} name={id} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined} className="h-11 rounded-xl bg-background" {...props} />
      {error && <p id={`${id}-error`} className="flex items-center gap-1.5 text-sm text-destructive"><AlertCircle className="size-3.5" aria-hidden />{error}</p>}
    </div>
  );
}

function StatusLine({ status }: { status: Status }) {
  if (status.kind === "ok") return <p role="status" className="flex items-center gap-1.5 text-sm text-accent2"><Check className="size-4" aria-hidden />{status.text}</p>;
  if (status.kind === "error") return <p role="alert" className="text-sm text-destructive">{status.text}</p>;
  return null;
}

function SubmitButton({ busy, children }: { busy: boolean; children: React.ReactNode }) {
  return (
    <button type="submit" disabled={busy}
      className="inline-flex h-11 items-center gap-2 rounded-xl bg-accent px-5 text-sm font-semibold text-on-accent transition-transform hover:bg-accent/90 active:scale-[0.97] disabled:opacity-60">
      {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}{children}
    </button>
  );
}

export function ProfileForms({ name, email, level }: { name: string; email: string; level: Level }) {
  const router = useRouter();

  // ---- details
  const [details, setDetails] = useState({ name, level });
  const [detailErrors, setDetailErrors] = useState<Record<string, string>>({});
  const [detailStatus, setDetailStatus] = useState<Status>({ kind: "idle" });
  async function saveDetails(e: React.FormEvent) {
    e.preventDefault();
    const parsed = profileSchema.safeParse(details);
    if (!parsed.success) return setDetailErrors(fieldErrors(parsed.error));
    setDetailErrors({});
    setDetailStatus({ kind: "saving" });
    const res = await send("/api/profile", "PATCH", parsed.data);
    if (!res.ok) {
      setDetailErrors(res.fields ?? {});
      return setDetailStatus({ kind: "error", text: res.error ?? "Could not save." });
    }
    setDetailStatus({ kind: "ok", text: "Profile saved." });
    router.refresh();
  }

  // ---- password
  const [pw, setPw] = useState({ currentPassword: "", newPassword: "" });
  const [pwErrors, setPwErrors] = useState<Record<string, string>>({});
  const [pwStatus, setPwStatus] = useState<Status>({ kind: "idle" });
  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    const parsed = passwordChangeSchema.safeParse(pw);
    if (!parsed.success) return setPwErrors(fieldErrors(parsed.error));
    setPwErrors({});
    setPwStatus({ kind: "saving" });
    const res = await send("/api/profile/password", "POST", parsed.data);
    if (!res.ok) {
      setPwErrors(res.fields ?? {});
      return setPwStatus({ kind: "error", text: res.error ?? "Could not change password." });
    }
    setPw({ currentPassword: "", newPassword: "" });
    setPwStatus({ kind: "ok", text: "Password changed." });
  }

  // ---- delete
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePw, setDeletePw] = useState("");
  const [deleteStatus, setDeleteStatus] = useState<Status>({ kind: "idle" });
  async function deleteAccount(e: React.FormEvent) {
    e.preventDefault();
    if (!deletePw) return setDeleteStatus({ kind: "error", text: "Enter your password to confirm." });
    setDeleteStatus({ kind: "saving" });
    const res = await send("/api/profile", "DELETE", { password: deletePw });
    if (!res.ok) return setDeleteStatus({ kind: "error", text: res.error ?? "Could not delete the account." });
    await signOut({ redirectTo: "/" });
  }

  return (
    <div className="flex flex-col gap-6">
      <Card title="Profile" description={`Signed in as ${email}.`}>
        <form onSubmit={saveDetails} noValidate className="flex flex-col gap-5">
          <Field id="name" label="Display name" value={details.name} error={detailErrors.name} autoComplete="name"
            onChange={(e) => setDetails((d) => ({ ...d, name: e.target.value }))} />
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1.5 text-sm font-medium">Default learner level</legend>
            <p className="-mt-1 mb-1 text-xs text-muted">New lessons in the generator start at this level.</p>
            <div role="radiogroup" aria-label="Default learner level" className="flex w-fit gap-1 rounded-xl border border-border p-1">
              {(["beginner", "intermediate"] as const).map((lv) => (
                <button key={lv} type="button" role="radio" aria-checked={details.level === lv} onClick={() => setDetails((d) => ({ ...d, level: lv }))}
                  className={cn("rounded-lg px-4 py-2 text-sm capitalize transition-colors", details.level === lv ? "bg-accent2 text-on-accent" : "text-muted hover:text-text")}>
                  {lv}
                </button>
              ))}
            </div>
          </fieldset>
          <div className="flex flex-wrap items-center gap-4">
            <SubmitButton busy={detailStatus.kind === "saving"}>Save profile</SubmitButton>
            <StatusLine status={detailStatus} />
          </div>
        </form>
      </Card>

      <Card title="Password" description="Use at least 8 characters. You stay signed in on this device.">
        <form onSubmit={changePassword} noValidate className="flex flex-col gap-5">
          <Field id="currentPassword" label="Current password" type="password" autoComplete="current-password" value={pw.currentPassword}
            error={pwErrors.currentPassword} onChange={(e) => setPw((p) => ({ ...p, currentPassword: e.target.value }))} />
          <Field id="newPassword" label="New password" type="password" autoComplete="new-password" value={pw.newPassword}
            error={pwErrors.newPassword} onChange={(e) => setPw((p) => ({ ...p, newPassword: e.target.value }))} />
          <div className="flex flex-wrap items-center gap-4">
            <SubmitButton busy={pwStatus.kind === "saving"}>Change password</SubmitButton>
            <StatusLine status={pwStatus} />
          </div>
        </form>
      </Card>

      <Card title="Delete account" description="Permanently deletes your account, saved lessons and quiz history. This cannot be undone." danger>
        <button type="button" onClick={() => { setDeleteOpen(true); setDeletePw(""); setDeleteStatus({ kind: "idle" }); }}
          className="inline-flex h-11 items-center gap-2 rounded-xl border border-destructive/70 px-5 text-sm font-semibold text-destructive transition-colors hover:bg-destructive/10">
          <Trash2 className="size-4" aria-hidden /> Delete my account
        </button>
      </Card>

      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="border-border bg-surface sm:max-w-md">
          <form onSubmit={deleteAccount} className="flex flex-col gap-4">
            <DialogHeader>
              <DialogTitle>Delete your account?</DialogTitle>
              <DialogDescription>All of your lessons and quiz results will be deleted. Enter your password to confirm.</DialogDescription>
            </DialogHeader>
            <Field id="deletePassword" label="Password" type="password" autoComplete="current-password" value={deletePw}
              onChange={(e) => setDeletePw(e.target.value)} />
            <StatusLine status={deleteStatus} />
            <DialogFooter>
              <button type="button" onClick={() => setDeleteOpen(false)} className="h-10 rounded-lg px-4 text-sm text-muted hover:text-text">Cancel</button>
              <button type="submit" disabled={deleteStatus.kind === "saving"}
                className="inline-flex h-10 items-center gap-2 rounded-lg bg-destructive px-4 text-sm font-semibold text-on-accent disabled:opacity-60">
                {deleteStatus.kind === "saving" && <Loader2 className="size-4 animate-spin" aria-hidden />} Delete account
              </button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
