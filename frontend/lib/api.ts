import type { Lesson, Plan } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Error codes the backend returns as {"error": code, "message": text}, plus "network" for no connection. */
export type ApiErrorCode =
  | "ai_busy" | "quota_exceeded" | "invalid_key" | "model_unavailable" | "bad_request" | "bad_plan"
  | "unsupported_topic" | "not_answered" | "clarify" | "invalid_request" | "tts_error" | "server_error" | "network" | "unknown";

/** Friendly text per code. Raw server or browser errors are never shown to the user. */
const FRIENDLY: Record<ApiErrorCode, string> = {
  ai_busy: "The AI is busy right now. Please try again in a moment.",
  quota_exceeded: "The free AI quota is used up for now. Please try again in a few minutes.",
  invalid_key: "The AI service is not set up correctly (API key). Ask the project owner to check backend/.env.",
  model_unavailable: "The configured AI models are not available. Ask the project owner to check GEMINI_MODELS.",
  bad_request: "The AI could not process this request. Try rephrasing the topic.",
  bad_plan: "The AI could not plan this lesson. Please try again or rephrase the topic.",
  unsupported_topic: "", // the server's message lists the supported topics, so it is shown as is
  not_answered: "Structura could not build a lesson that fully answers this question. Try asking it a different way.",
  clarify: "Could you say a little more? Name the data structure and what you want to know about it.",
  invalid_request: "That request was not valid. Please check the topic and try again.",
  tts_error: "The narration voice is not available. Ask the project owner to run setup.sh.",
  server_error: "Something went wrong on the server. Please try again.",
  network: "Cannot reach the lesson server. Make sure the backend is running, then try again.",
  unknown: "Something went wrong. Please try again.",
};

/** Codes where trying again later can succeed. */
export const RETRYABLE: ReadonlySet<ApiErrorCode> = new Set(["ai_busy", "quota_exceeded", "server_error", "network", "bad_plan"]);

export class ApiError extends Error {
  constructor(public code: ApiErrorCode, message: string) {
    super(message);
  }
}

function toCode(value: unknown): ApiErrorCode {
  return typeof value === "string" && value in FRIENDLY ? (value as ApiErrorCode) : "unknown";
}

async function post<T>(path: string, body: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("network", FRIENDLY.network);
  }
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { error?: unknown; message?: unknown } | null;
    const code = toCode(data?.error ?? (res.status === 503 ? "ai_busy" : res.status === 429 ? "quota_exceeded" : undefined));
    const serverText = typeof data?.message === "string" ? data.message : "";
    // these two messages are written for the user by the backend (supported topics / what the lesson could not cover)
    const ownText = (code === "unsupported_topic" || code === "not_answered" || code === "clarify") && serverText;
    throw new ApiError(code, ownText ? serverText : FRIENDLY[code]);
  }
  return res.json() as Promise<T>;
}

/** Turns anything thrown by the API helpers into a user-safe message. */
export function friendlyError(e: unknown): { code: ApiErrorCode; message: string } {
  return e instanceof ApiError ? { code: e.code, message: e.message } : { code: "unknown", message: FRIENDLY.unknown };
}

export function createLesson(topic: string, level: "beginner" | "intermediate") {
  return post<Lesson>("/lesson", { topic, level });
}

export function reviseLesson(plan: Plan, sceneId: number | null, instruction: string, scenes?: Lesson["scenes"]) {
  // the current scenes come back unchanged except the revised one
  return post<Lesson>("/revise", { plan, scene_id: sceneId, instruction, scenes });
}

export const audioUrl = (path: string) => `${API_URL}${path}`;
