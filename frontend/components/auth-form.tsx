"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { signIn } from "next-auth/react";
import { AnimatePresence, motion } from "motion/react";
import { AlertCircle, Check, Loader2 } from "lucide-react";
import type { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { fieldErrors, loginSchema, signupSchema } from "@/lib/validation";

type Mode = "login" | "signup";

const LOGIN_ERRORS: Record<string, string> = {
  credentials: "Incorrect email or password.",
  rate_limited: "Too many failed attempts. Wait 15 minutes and try again.",
  db_unavailable: "The database is unavailable. Check MONGODB_URI and try again.",
};

/**
 * Where to go after login. Auth.js passes a full URL, links may pass a path. Only the path is kept,
 * so a crafted callbackUrl can never send the user to another site. Same result on server and client.
 */
function safeCallback(url: string | null): string {
  if (!url) return "/dashboard";
  try {
    const target = new URL(url, "http://localhost");
    if (target.pathname === "/login" || target.pathname === "/signup") return "/dashboard";
    return target.pathname + target.search;
  } catch {
    return "/dashboard";
  }
}

function Field({ id, label, error, valid, ...props }: React.ComponentProps<typeof Input> & { id: string; label: string; error?: string; valid?: boolean }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium">{label}</label>
      <div className="relative">
        <Input id={id} name={id} aria-invalid={Boolean(error)} aria-describedby={error ? `${id}-error` : undefined}
          className={`h-12 rounded-xl bg-surface pr-10 text-base transition-colors ${valid && !error ? "border-accent2/60" : ""}`} {...props} />
        <AnimatePresence>
          {valid && !error && (
            <motion.span initial={{ scale: 0.5, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.5, opacity: 0 }}
              className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-accent2" aria-hidden>
              <Check className="size-4" />
            </motion.span>
          )}
        </AnimatePresence>
      </div>
      <AnimatePresence initial={false}>
        {error && (
          <motion.p id={`${id}-error`} initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
            className="flex items-center gap-1.5 overflow-hidden text-sm text-destructive">
            <AlertCircle className="size-3.5 shrink-0" aria-hidden />{error}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const callbackUrl = safeCallback(useSearchParams().get("callbackUrl"));
  const [fields, setFields] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [valid, setValid] = useState<Record<string, boolean>>({});
  const schema = mode === "signup" ? signupSchema : loginSchema;

  /** Inline validation: check one field when the user leaves it (empty fields are left alone). */
  function checkField(e: React.FocusEvent<HTMLInputElement>) {
    const { name, value } = e.currentTarget;
    const fieldSchema = (schema.shape as Record<string, z.ZodType>)[name];
    if (!value || !fieldSchema) return;
    const result = fieldSchema.safeParse(value);
    setFields((f) => {
      const next = { ...f };
      if (result.success) delete next[name];
      else next[name] = result.error.issues[0]?.message ?? "Invalid value.";
      return next;
    });
    setValid((v) => ({ ...v, [name]: result.success && mode === "signup" }));
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(e.currentTarget)) as Record<string, string>;
    const parsed = (mode === "signup" ? signupSchema : loginSchema).safeParse(data);
    if (!parsed.success) {
      setFields(fieldErrors(parsed.error));
      setFormError(null);
      return;
    }
    setFields({});
    setFormError(null);
    setLoading(true);
    try {
      if (mode === "signup") {
        const res = await fetch("/api/signup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(parsed.data),
        });
        if (!res.ok) {
          const body = (await res.json().catch(() => ({}))) as { error?: string; fields?: Record<string, string> };
          setFields(body.fields ?? {});
          setFormError(body.error ?? "Sign up failed. Try again.");
          return;
        }
      }
      const result = await signIn("credentials", { email: parsed.data.email, password: parsed.data.password, redirect: false });
      if (!result || result.error) {
        setFormError(LOGIN_ERRORS[result?.code ?? "credentials"] ?? LOGIN_ERRORS.credentials);
        return;
      }
      router.push(callbackUrl);
      router.refresh();
    } catch {
      setFormError("Something went wrong. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }

  const isSignup = mode === "signup";
  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      {formError && (
        <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-destructive/60 bg-destructive/10 p-3.5 text-sm">
          <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
          <span>{formError}</span>
        </div>
      )}
      {isSignup && <Field onBlur={checkField} valid={valid.name} id="name" label="Name" autoComplete="name" error={fields.name} disabled={loading} />}
      <Field onBlur={checkField} valid={valid.email} id="email" label="Email" type="email" autoComplete="email" error={fields.email} disabled={loading} />
      <Field onBlur={checkField} valid={valid.password} id="password" label="Password" type="password" autoComplete={isSignup ? "new-password" : "current-password"}
        error={fields.password} disabled={loading} />
      {isSignup && !fields.password && <p className="-mt-2 text-xs text-muted">At least 8 characters.</p>}
      <Button type="submit" disabled={loading} className="mt-1 h-12 rounded-xl text-base font-semibold transition-transform active:scale-[0.98]">
        {loading && <Loader2 className="animate-spin" aria-hidden />}
        {loading ? (isSignup ? "Creating account..." : "Logging in...") : isSignup ? "Create account" : "Log in"}
      </Button>
      <p className="text-center text-sm text-muted">
        {isSignup ? "Already have an account? " : "New to Structura? "}
        <Link href={`${isSignup ? "/login" : "/signup"}${callbackUrl !== "/dashboard" ? `?callbackUrl=${encodeURIComponent(callbackUrl)}` : ""}`}
          className="font-medium text-accent2 underline-offset-4 hover:underline">
          {isSignup ? "Log in" : "Sign up"}
        </Link>
      </p>
    </form>
  );
}
