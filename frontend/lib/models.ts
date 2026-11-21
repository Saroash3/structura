import "server-only";
import { Schema, model, models, type InferSchemaType, type Model, type Types } from "mongoose";

export const LEVELS = ["beginner", "intermediate"] as const;

// ---------------------------------------------------------------- users
const userSchema = new Schema(
  {
    name: { type: String, required: true, trim: true, maxlength: 60 },
    email: { type: String, required: true, unique: true, lowercase: true, trim: true },
    passwordHash: { type: String, required: true },
    level: { type: String, enum: LEVELS, default: "beginner" },
  },
  { timestamps: { createdAt: true, updatedAt: false } },
);

// ---------------------------------------------------------------- lessons
const lessonSchema = new Schema(
  {
    userId: { type: Schema.Types.ObjectId, ref: "User", required: true, index: true },
    title: { type: String, required: true, trim: true, maxlength: 120 }, // renameable; starts as the topic
    topic: { type: String, required: true, trim: true },
    structure: { type: String, required: true },
    level: { type: String, enum: LEVELS, default: "beginner" },
    plan: { type: Schema.Types.Mixed, required: true }, // the verified scene plan
    audioDurations: { type: [Number], default: [] },
    snapshot: { type: Schema.Types.Mixed }, // full verified lesson (scenes, states, quiz) for instant replay
    pinned: { type: Boolean, default: false },
  },
  // minimize: false keeps empty objects such as a state's `last: {}` (the default would delete them from the snapshot)
  { timestamps: { createdAt: true, updatedAt: true }, minimize: false },
);

// ---------------------------------------------------------------- quiz results
const quizResultSchema = new Schema(
  {
    userId: { type: Schema.Types.ObjectId, ref: "User", required: true, index: true },
    lessonId: { type: Schema.Types.ObjectId, ref: "Lesson" },
    topic: { type: String, required: true },
    structure: { type: String },
    score: { type: Number, required: true, min: 0 },
    total: { type: Number, required: true, min: 1 },
  },
  { timestamps: { createdAt: true, updatedAt: false } },
);

export type UserDoc = InferSchemaType<typeof userSchema> & { _id: Types.ObjectId; createdAt: Date };
export type LessonDoc = InferSchemaType<typeof lessonSchema> & { _id: Types.ObjectId; createdAt: Date; updatedAt: Date };
export type QuizResultDoc = InferSchemaType<typeof quizResultSchema> & { _id: Types.ObjectId; createdAt: Date };

export const User: Model<UserDoc> = (models.User as Model<UserDoc>) ?? model<UserDoc>("User", userSchema);
export const Lesson: Model<LessonDoc> = (models.Lesson as Model<LessonDoc>) ?? model<LessonDoc>("Lesson", lessonSchema);
export const QuizResult: Model<QuizResultDoc> =
  (models.QuizResult as Model<QuizResultDoc>) ?? model<QuizResultDoc>("QuizResult", quizResultSchema);
