/**
 * Real numbers about Structura, mirrored from the backend code (not marketing estimates).
 * If you change the backend, update these too.
 */
export const FACTS = {
  /** backend/structures.py: STRUCTURES (array, queue, stack, linked_list, binary_tree, graph_bfs, bubble_sort) */
  structures: 7,
  /** backend/quiz.py: ASKS has 3 questions per structure, answers computed by running the structure */
  quizQuestions: 3,
  /** backend/lesson.py: MIN_SECONDS */
  minLessonSeconds: 30,
  /** backend/verifier.py: verify_scene never returns an unverified scene (LLM fix, then code template) */
  verifiedPercent: 100,
} as const;

/** Example prompts that the planner supports (used by the landing marquee). */
export const EXAMPLE_PROMPTS = [
  "how does a queue work",
  "show BFS on this graph",
  "explain a linked list delete",
  "push and pop on a stack",
  "insert into a binary search tree",
  "show bubble sort step by step",
  "how does an array insert work",
  "search a binary search tree",
  "dequeue until the queue is empty",
  "breadth first search level by level",
] as const;
