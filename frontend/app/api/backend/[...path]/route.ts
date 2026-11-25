/**
 * Same-origin proxy to the FastAPI backend (lessons, revisions, audio, video export).
 *
 * In production the backend runs on the team laptop behind a tunnel (BACKEND_URL, server-only). The browser only ever
 * talks to this site, so there is no CORS or mixed-content problem, and the tunnel's "visit site" warning page (shown
 * to browsers by free ngrok) is skipped with its header. Set NEXT_PUBLIC_API_URL=/api/backend to use it.
 */
import type { NextRequest } from "next/server";

export const maxDuration = 300; // a new lesson can take up to a minute when Gemini retries

const PASS_REQUEST = ["content-type", "accept", "range"];
const PASS_RESPONSE = ["content-type", "content-length", "content-disposition", "content-range", "accept-ranges",
  "cache-control", "x-audio-duration"];

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const base = process.env.BACKEND_URL;
  if (!base) {
    return Response.json({ error: "server_error", message: "The backend is not configured (BACKEND_URL)." }, { status: 500 });
  }
  const { path } = await ctx.params;
  const target = `${base.replace(/\/+$/, "")}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const headers = new Headers({ "ngrok-skip-browser-warning": "1" });
  for (const h of PASS_REQUEST) {
    const v = req.headers.get(h);
    if (v) headers.set(h, v);
  }
  let res: Response;
  try {
    res = await fetch(target, {
      method: req.method,
      headers,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return Response.json({ error: "network", message: "The lesson server is offline right now. Please try again later." }, { status: 503 });
  }
  const out = new Headers();
  for (const h of PASS_RESPONSE) {
    const v = res.headers.get(h);
    if (v) out.set(h, v);
  }
  if ((res.headers.get("content-type") ?? "").includes("text/html")) {
    // the tunnel is down or showing its own page: never pass a foreign HTML page to the app
    return Response.json({ error: "network", message: "The lesson server is offline right now. Please try again later." }, { status: 503 });
  }
  return new Response(res.body, { status: res.status, headers: out });
}

export const GET = forward;
export const POST = forward;
export const HEAD = forward;
