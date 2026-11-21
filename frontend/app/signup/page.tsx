import type { Metadata } from "next";
import { AuthShell } from "@/components/auth-shell";

export const metadata: Metadata = { title: "Sign up | Structura" };

export default function SignupPage() {
  return <AuthShell mode="signup" />;
}
