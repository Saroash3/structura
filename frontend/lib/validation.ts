import { z } from "zod";

export const emailSchema = z.string().trim().toLowerCase().email("Enter a valid email address.").max(200);
export const passwordSchema = z
  .string()
  .min(8, "Password must be at least 8 characters.")
  .max(128, "Password must be at most 128 characters.");

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, "Enter your password.").max(128),
});

export const signupSchema = z.object({
  name: z.string().trim().min(2, "Name must be at least 2 characters.").max(60, "Name is too long."),
  email: emailSchema,
  password: passwordSchema,
});

export type SignupInput = z.infer<typeof signupSchema>;

/** First error message per field, for showing under inputs. */
export function fieldErrors(error: z.ZodError): Record<string, string> {
  const out: Record<string, string> = {};
  for (const issue of error.issues) {
    const key = String(issue.path[0] ?? "form");
    out[key] ??= issue.message;
  }
  return out;
}

// ---------------------------------------------------------------- lessons, quiz results, profile
const STRUCTURES = ["array", "queue", "stack", "linked_list", "binary_tree", "graph_bfs", "graph_dfs", "bubble_sort", "insertion_sort"] as const;
export const levelSchema = z.enum(["beginner", "intermediate"]);

/** Shape check for a verified lesson coming back from the FastAPI backend (extra fields kept). */
export const lessonPayloadSchema = z.looseObject({
  topic: z.string().min(1).max(200),
  structure: z.enum(STRUCTURES),
  level: levelSchema.optional(),
  plan: z.looseObject({ topic: z.string(), structure: z.enum(STRUCTURES), scenes: z.array(z.looseObject({})).min(1).max(60) }),
  scenes: z.array(z.looseObject({ duration: z.number().nonnegative(), audio_url: z.string() })).min(1).max(60),
  total_duration: z.number().nonnegative(),
});

export const lessonPatchSchema = z
  .object({
    title: z.string().trim().min(1, "Title cannot be empty.").max(120, "Title is too long.").optional(),
    pinned: z.boolean().optional(),
  })
  .refine((v) => v.title !== undefined || v.pinned !== undefined, "Nothing to update.");

export const quizResultSchema = z.object({
  lessonId: z.string().max(40).nullable().optional(),
  topic: z.string().trim().min(1).max(200),
  structure: z.enum(STRUCTURES).optional(),
  score: z.number().int().min(0),
  total: z.number().int().min(1).max(20),
}).refine((v) => v.score <= v.total, "Score cannot exceed total.");

export const profileSchema = z.object({
  name: z.string().trim().min(2, "Name must be at least 2 characters.").max(60, "Name is too long."),
  level: levelSchema,
});

export const passwordChangeSchema = z.object({
  currentPassword: z.string().min(1, "Enter your current password.").max(128),
  newPassword: passwordSchema,
});
