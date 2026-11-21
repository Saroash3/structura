/** "growth" is a growth table of real counts, shown by complexity lessons (never a lesson's main structure). */
export type Structure = "array" | "queue" | "stack" | "linked_list" | "binary_tree" | "graph_bfs" | "graph_dfs" | "bubble_sort"
  | "insertion_sort" | "growth" | "array_2d" | "dyn_array" | "jagged_array";

/** A value (number) or a node label (string, e.g. "A" in a user's graph). */
export type Label = number | string;

export interface Op {
  op: string;
  args: Label[];
}

/** Details of the last op, computed by the backend's real data structure. */
export interface LastOp {
  op?: string;
  args?: Label[];
  value?: Label;
  removed?: Label;
  index?: number;
  path?: number[];
  parent?: number | null;
  edge?: [Label, Label];
  enqueued?: Label[];
  /** DFS: neighbours pushed onto the stack by this visit */
  pushed?: Label[];
  compared?: [number, number];
  values?: number[];
  swapped?: boolean;
  finished?: boolean;
  shifted?: number;
  old?: number;
  /** linked list: the node before / after the changed node (null = none) */
  prev?: Label | null;
  next?: Label | null;
  /** false when a search or delete did not find the value (the walk reached null) */
  found?: boolean;
  /** complexity counters: items touched by an O(1) op, items checked so far by a scan or walk, neighbours checked by a BFS visit */
  touched?: number;
  checked?: number;
  neighbours?: number;
  /** array scan (linear search): the value searched for */
  target?: number;
  pass_done?: boolean;
  /** 2D / jagged arrays: the cell read or written */
  row?: number;
  col?: number;
  length?: number;
  /** static vs dynamic array: a full static array refuses a value; a full dynamic array doubles and copies */
  refused?: boolean;
  resized?: boolean;
  old_capacity?: number;
  new_capacity?: number;
  copied?: number;
  /** which kind of linked list / queue is shown */
  variant?: string;
}

export type Role = "setup" | "core" | "edge_case" | "recap";

/** One teaching point of the answer; scenes are derived from these (only the demo may span several scenes). */
export interface AnswerPoint {
  id: string;
  kind: string; // definition, analogy, rule, demo, uses, recap, goal, steps, explain, edge
  point: string;
  /** question-driven lessons: the answer requirement this point covers */
  requirement_id?: string | null;
  visual: string;
}

/** What the user actually asked; every lesson is organised around it. */
export interface Analysis {
  structure: Structure;
  intent: "what_is" | "how_op" | "compare" | "trace_on_input" | "why" | "complexity" | "question";
  focus: string;
  position?: string | null;
  focus_text: string;
  must_answer: string;
  core_ops: string[];
  compare_with?: Structure | null;
  /** complexity questions: what is counted (bubble_sort, linear_search, bfs, stack_push, ...) */
  algorithm?: string | null;
  /** question-driven lessons: what a correct answer must contain, and the terms it must use */
  requirements?: { id: string; text: string; evidence: string }[];
  key_terms?: string[];
}

export interface TreeNode {
  value: number;
  depth: number;
  left: number | null;
  right: number | null;
  x: number;
  y: number;
}

export interface GraphNode {
  value: Label;
  x: number;
  y: number;
}

export interface State {
  kind: Structure;
  items: Label[];
  size?: number;
  last: LastOp;
  front?: number | null;
  back?: number | null;
  top?: number | null;
  head?: number | null;
  tail?: number | null;
  root?: number | null;
  height?: number;
  nodes?: (TreeNode | GraphNode)[];
  edges?: [Label, Label][];
  queue?: Label[];
  discovered?: Label[];
  order?: Label[];
  current?: Label | null;
  /** linked list: index of the node the walk is standing on */
  current_index?: number | null;
  pointers?: { value: Label; next: Label | null }[];
  start?: Label | null;
  sorted_from?: number;
  is_sorted?: boolean;
  /** insertion sort: items[:sorted_upto] are sorted among themselves */
  sorted_upto?: number;
  /** graph DFS: the stack of nodes waiting to be visited (top = last) */
  stack?: Label[];
  /** bubble sort: real counts so far, and comparisons made in each pass */
  comparisons?: number;
  swaps?: number;
  pass_counts?: number[];
  passes?: number;
  early_exit?: boolean;
  /** graph BFS: work so far */
  visits?: number;
  checks?: number;
  edge_count?: number;
  /** array linear search: indexes checked so far */
  scan?: { target: number; checked: number[]; done: boolean };
  /** growth table: the real count for each input size n */
  algo?: string | null;
  /** growth tables: one row per n (2D / jagged arrays send a row count here instead; their views use `cells`) */
  rows?: { n: number; count: number }[];
  /** 2D and jagged arrays: the values row by row */
  cells?: number[][];
  cols?: number;
  /** static vs dynamic array */
  capacity?: number;
  mode?: "static" | "dynamic" | "";
  copies?: number;
  resizes?: number;
  full?: boolean;
  /** linked list: singly | doubly | circular; queue: simple | circular | priority | deque */
  variant?: string;
}

export interface Scene {
  id: number;
  ops: Op[];
  narration: string;
  before: State;
  steps: State[];
  state: State;
  verified: boolean;
  narration_source: "llm" | "llm-fixed" | "llm-judge-fixed" | "template";
  audio_url: string;
  /** beginner lessons: the running analogy this scene uses, e.g. "like a line of people" */
  analogy?: string;
  /** parts of the picture the narration names (root, leaf, head, tail): the stage highlights them */
  named?: string[];
  duration: number;
  speed: number;
  role?: Role;
  /** the answer point this scene teaches */
  point_id?: string;
  kind?: string;
  /** set only when this scene runs on a second structure (compare lessons) */
  structure?: Structure | null;
}

export interface QuizQuestion {
  question: string;
  options: string[];
  answer_index: number;
  explanation: string;
  kind?: "principle" | "real_world" | "vocab" | "trace" | "complexity" | "core";
}

export interface PlanScene {
  id: number;
  ops: Op[];
  narration: string;
  speed: number;
  role?: Role;
  structure?: Structure;
  point_id?: string;
  kind?: string;
}

export interface Plan {
  topic: string;
  structure: Structure;
  scenes: PlanScene[];
  analysis?: Analysis;
  answer_points?: AnswerPoint[];
}

export interface Lesson {
  topic: string;
  structure: Structure;
  level?: string;
  plan: Plan;
  scenes: Scene[];
  total_duration: number;
  quiz?: QuizQuestion[];
  analysis?: Analysis;
  answer_points?: AnswerPoint[];
  /** share of the lesson's duration spent on core scenes (0..1) */
  core_share?: number;
  revised?: { scene_id: number; change: "speed" | "narration" | "none"; before?: string; after?: string; message?: string };
  /** "Verified" means every fact is true; this means the question is answered (each requirement and its scenes) */
  answer_check?: { passed: boolean; shape?: string | null; judge?: boolean | null; method?: string;
                   requirements: { id: string; text: string; scenes: number[] }[] };
}
