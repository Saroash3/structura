import bcrypt from "bcryptjs";
import { NextResponse } from "next/server";
import { connectDB } from "@/lib/db";
import { User } from "@/lib/models";
import { fieldErrors, signupSchema } from "@/lib/validation";

export async function POST(request: Request) {
  const body: unknown = await request.json().catch(() => null);
  const parsed = signupSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Please fix the highlighted fields.", fields: fieldErrors(parsed.error) }, { status: 400 });
  }
  const { name, email, password } = parsed.data;

  try {
    await connectDB();
  } catch {
    return NextResponse.json({ error: "The database is unavailable. Check MONGODB_URI and try again." }, { status: 503 });
  }

  if (await User.exists({ email })) {
    return NextResponse.json({ error: "An account with this email already exists.", fields: { email: "Already registered. Log in instead." } }, { status: 409 });
  }
  const passwordHash = await bcrypt.hash(password, 12);
  try {
    await User.create({ name, email, passwordHash });
  } catch (err: unknown) {
    // unique index race: two signups with the same email at once
    if (typeof err === "object" && err !== null && "code" in err && err.code === 11000) {
      return NextResponse.json({ error: "An account with this email already exists." }, { status: 409 });
    }
    throw err;
  }
  return NextResponse.json({ ok: true }, { status: 201 });
}
