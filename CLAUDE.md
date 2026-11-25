# Structura: project guide for future sessions

**What it is:** Structura is NLP Project 1, the Data Structure Explainer, **due 30 Nov 2026**. The team is Saroash Waseem (22i-2609) and Agha Ahsan (21i-1117).

A user asks a question about a data structure. Structura answers with an animated, narrated lesson and a short quiz. The structures are array, queue, stack, linked list, binary search tree, BFS on a graph, and bubble sort.

> **PRIORITY RULE (whole project): the answer to the user's exact question comes first.** Diagrams, animation and demos exist only to support that answer. A lesson that does not answer the question is a failed lesson, even if every sentence is verified. Never run a generic demo of the structure when the question asks for something else.
>
> **PRIORITY RULE (whole project): every explanation must be understandable to a total beginner who has never programmed, and must stay on the question.** Teach slowly and simply. Verified facts are necessary but not sufficient: the sentences must also be clear.
>
> **Answer quality comes first.** Diagrams and animation exist only to support the answer to the user's question. Never add a scene just to show an operation or an animation. Every scene must teach a specific point that helps answer the question. The planner outlines the answer first (`answer_points`); scenes and visuals are derived from those points.

## Stack

| Part | Technology |
|---|---|
| Backend | FastAPI, Python **3.14** venv at `backend/.venv` (3.15 lacks wheels) |
| LLM | Gemini through the `google-genai` SDK |
| Text to speech | Local Piper with the `en_US-lessac-medium` voice, stored in `backend/voices/` |
| Video export | Playwright (Python) headless Chromium + ffmpeg/ffprobe (`winget install Gyan.FFmpeg`), all local |
| Backend tests | pytest |
| Frontend | Next.js 16 (Turbopack, `cacheComponents: true`, `proxy.ts` instead of middleware), Tailwind, shadcn base-nova (Base UI), Motion (`motion/react`), Magic UI and Aceternity pieces (patched copies in `components/ui`) |
| Auth and data | Auth.js v5 Credentials with JWT, bcryptjs, zod v4, Mongoose on MongoDB Atlas |

## Running it

```bash
bash setup.sh                                   # one-time: venv, pip packages, Piper voice, npm install
cd backend && .venv/Scripts/uvicorn main:app    # http://localhost:8000 (on Windows --reload can hang; restart by hand)
cd frontend && npm run dev                      # usually http://localhost:3001 (port 3000 is taken by another app on this machine)
cd backend && .venv/Scripts/python -m pytest -q # backend tests
cd backend && .venv/Scripts/python eval_lessons.py --help   # live evaluation (calls Gemini + Piper)
cd frontend && npx tsc --noEmit && npm run lint # frontend checks
```

Video export needs ffmpeg + ffprobe (found on PATH, `$FFMPEG_DIR` or the winget folder) and `playwright install chromium`, and the frontend running: the backend records the frontend's `/render` page.

Environment files are gitignored. Never print, copy or commit their values.

- `backend/.env` sets `GEMINI_API_KEY`, `GEMINI_MODELS` (a comma-separated fallback list) and `GEMINI_MODEL`. The `gemini-2.5-*` models return 404 for this key, so use `gemini-3.5-flash-lite` and newer.
- `frontend/.env.local` sets `MONGODB_URI`, `AUTH_SECRET` and the optional `NEXT_PUBLIC_API_URL`.
- Placeholder versions are in `backend/.env.example` and `frontend/.env.example`.

## Architecture (backend/)

- **`concepts.py`** says what a good answer contains, per structure: the outline of a "what is" answer (`WHAT_IS`, `WHAT_IS_POINTS`, `WHAT_IS_DEMO`), the key rule plus keyword groups plus proof sentence (`PRINCIPLE`, `PRINCIPLE_FOCUS`), real-world uses (`USES`), `GLOSSARY`, `JARGON` (must be explained before use), and quiz answer keys.
  - Beginner mode: one running analogy per structure (`ANALOGY`: tag, analogy words, picture), the needs-definition terms (`NEEDS_DEFINITION`), the fixed plain glossary, picture first and name second (`PLAIN`), banned filler words (`FILLER`), and the problem-then-fix runs for WHY questions (`WHY`, `WHY_QUESTION`).
  - Text in `PLAIN` and `WHY` may ship as narration, so it contains no numbers or number words ("a single box", not "one box").
- **`clarity.py`** is the clarity gate for beginner lessons:
  - `lesson_clarity` limits each scene with ops to 2 sentences and every sentence to 25 words (a chain or bracketed list counts as one word);
  - every needs-definition term is explained before use, and never with another unexplained term;
  - it also catches garbled "in memory, which means …" glosses, glossary sentences glued to a step with "so" or "because", FIFO/LIFO before the demo, and filler;
  - the running analogy must appear in at least 70% of demo scenes; a scene on a second structure uses that structure's own analogy;
  - helpers: `define_first` (puts the glossary definition in front of a correct narration that only missed one, with no LLM call), `plain_text`, `short_sentences`, `split_text`, `analogy_tag`.
- **`plain.py`** holds the beginner op templates: the step in analogy words, then its name, then the true state, in at most 2 sentences. `verifier.generic_template` checks them before use.
- **`focus.py`** analyses the question: structure, intent (`what_is | how_op | compare | trace_on_input | why`), focus, `must_answer` and core ops.
  - It holds a catalogue for each focus: intro and recap sentences, required concepts, detail and edge-case sentences, and off-topic patterns.
  - `shape()` organises the LLM's plan around the focus. It assigns roles, merges the setup into one `init` scene, builds core ops such as the hop-by-hop walk, and drops scenes that don't serve the focus.
  - `skeleton()` builds a lesson in code, and `compare_skeleton()` builds the array-versus-linked-list lesson.
- **`planner.py`** asks the LLM for a plan that contains only operations, never states. The prompt includes the analysis, an intent template and a few-shot example for a different structure. Plans are validated with Pydantic and retried twice.
  - `conform_to_given()` forces the user's own data into the plan.
  - `fix_scenes_batch()` makes one LLM call that repairs every failing scene, given each scene's true state, role and note.
- **`structures.py`** has the real implementations. LinkedList has `init`, a `walk` cursor that moves one hop at a time, `insert_after`, a `prev`/`next` on every op, and `found: False` for missing values. Array, queue, stack and BST also have `init`.
- **`verifier.py`** simulates the ops and checks every number and claim against the true state.
  - Specificity: each scene must name its required facts.
  - Linked list pointers: `POINTS_TO`, `NEXT_IS`, `SKIPPED` and `CHAIN` claims. Bracket lists are banned for linked lists.
  - Focus: `focus_errors` checks that the intro leads into the question, the recap answers it and nothing is off-topic.
  - Templates are the fallback and always pass the checks.
- **`lesson.py`** runs the pipeline: verify all scenes (cached and batch-repaired), add missing focus concepts, then enforce the budget. Core scenes must fill at least 50% of the duration and the lesson must last at least 30 s. Narration goes to Piper with `->` spoken as "then".
- **`quiz.py`** has `focus_questions()`: at least 2 of the 3 questions test the focus, using the lesson's own data. The answers are computed by code. The LLM may only reword a question, and the rewording is rejected if any number or label changes.
- **`revision.py`** changes one scene (its speed or narration). A narration rewrite is checked with `candidate_errors` (verifier + clarity gate, including problems it would cause in other scenes) BEFORE it goes in, retried once at a higher temperature with the reasons, and refused honestly (`change: "none"`, the NO_CHANGE message) if it still fails or is a near-copy (similarity above 0.9). Templates never stand in for a requested rewrite. With `scenes` (the viewer's current scenes) every other scene comes back byte-identical; the response carries `before`/`after` for the UI.
- **`tts.py`** wraps Piper and caches audio in `audio_cache/`.
- **`video.py`** exports an MP4: the lesson is stored under a job id; headless Chromium records the frontend's `/render?job=` page (white until `__renderStart()`, then the same Stage and `frameAt` timing as the player, then a quiz slide with the verified answers); the scene WAVs are joined so each lasts exactly `duration / speed`; ffmpeg finds the first non-white frame (`negate,blackdetect`) and muxes H.264 + AAC 1280x720 yuv420p; ffprobe checks streams and durations (within 0.5 s). Cached in `video_cache/` by lesson id + `content_hash`. `local_api()` serves the job store for scripts and tests.
- **`complexity.py`** handles time complexity lessons. It holds the algorithm registry (`ALGOS`) and builds the lesson in code from answer points to scenes. `narrate()` writes each scene from its true state, and `facts()` lists the numbers the verifier allows.
- **`llm.py`** handles reliability: model fallback, exponential backoff, a 45 s timeout and a semaphore of 2. It returns error codes such as `ai_busy` and `quota_exceeded`, and keeps a disk cache of responses.
- **`main.py`** serves `/lesson`, `/revise`, `/export`, `/export/{id}`, `/export/{id}/lesson`, `/export/{id}/video`, `/tts`, `/audio/{name}` and `/health` (which reports `video_export` tools), with JSON errors shaped as `{error, message}`. A lifespan hook warns at startup when ffmpeg or Playwright is missing.

Frontend:

- `app/` holds the pages: landing, `/app` (the generator), `/dashboard`, `/lesson/[id]`, `/profile`, `/login` and `/signup`.
- `components/` holds `player`, `stage` and `quiz`, and `generator` (which auto-saves lessons). `video-export` is the Download video button (progress, errors), under the player in `/app` and `/lesson/[id]`. `render-view` (route `/render`, public) is what the exporter records. `stage` highlights the parts a scene names (`scene.named`: LEAF/ROOT on trees).
- `lib/data.ts` is the only database access, always scoped by userId. `lib/api.ts` handles friendly errors and retries.

## Rules we decided (do not break)

0. **Answer quality comes first** (see the priority rule at the top). Every scene maps to exactly one answer point. A demo must say what it proves about the rule. Plain words come before jargon, and there is no padding or repetition.
1. **The LLM only plans operations; code computes every state and verifies every sentence.** Unverified narration never ships: it is repaired, and templates are the fallback.
2. **TTS is local Piper**, not a cloud service. **Video export is local too** (headless Chromium + ffmpeg), never an external video API.
3. **Palette** (dark only, no gradients, no emojis, contrast ≥ 4.5:1):

   | Token | Hex |
   |---|---|
   | bg | `#121212` |
   | surface | `#1E1E1E` |
   | stage | `#0D0D0D` |
   | border | `#404040` |
   | text | `#F2F2F2` |
   | muted | `#A8A8A8` |
   | accent | `#FF7A1A` |
   | accent2 | `#4CC9F0` |
   | text on accent | `#000000` |

4. **The user's labels and input are preserved exactly**: graph labels are strings, and values the user gives are used in order.
5. **Narration names the concrete state**, for example "Visit B. Queue is now [C, D]." Linked lists are described with pointers: "20 now points to 40, so 30 is skipped. head -> 10 -> 20 -> 40 -> null." In beginner mode the same facts are told in the analogy: "box 20's note now points to box 40, so box 30 is skipped".
5b. **Beginner mode is the default.** Each scene teaches one new idea in at most 2 sentences of at most 25 words. Use everyday words, picture first and name second, and keep ONE running analogy restated in every demo step. Terms come from the fixed plain glossary. A WHY question shows the problem before the fix. There is no filler. The clarity judge reuses the existing judge call, so there are still 3 LLM calls per new lesson.
6. **Every lesson answers the user's actual question** with a design built around its focus:
   - Every scene has a role: setup, core, edge_case or recap.
   - There are at most 2 setup scenes.
   - Core scenes fill at least 50% of the duration.
   - The intro is about 25 words and leads into the question; only `what_is` lessons open with a definition.
   - The recap restates the answer.
   - There are no unrelated facts.
   - The quiz tests the focus.
7. **Keep LLM calls low**: one planning call plus batched repairs.
8. **Never write secrets** (API keys, passwords, connection strings) into any file except the two gitignored env files.

## Current status (2026-11-22, later)

**Answer fit for any question shape, and a fast export: done.**
- **Root cause of "how many types of array" giving a generic "what is an array" lesson:** the analysis call answered `{"unsupported": true}`; `planner.make_plan` then built a focused skeleton (the old focus pipeline, intent `what_is`) with NO coverage gate (`judge = null`), and that run used 4 LLM calls. Fixes:
  - the prompt classifies the question `shape` and says types and variants of supported structures ARE supported;
  - `answer.question_shape` validates the shape from the wording (`STRONG_SHAPES` win);
  - `lesson.build_lesson` asks a clarifying question for vague input (`NeedsClarification`, API error `clarify`) and never turns a list question into a generic lesson;
  - the old pipeline is only used for the shapes it can answer, with one repair round, no quiz rewording, and a key-noun check (`answer.missing_nouns`).
- **Shapes:**
  - `list`: `_list_plan_from`, one requirement and one scene per item from `concepts.VARIANTS`, the count when asked (`count_facts` are verifier facts), and a recap that names every item;
  - `compare` and `when`: `_compare_plan_from`, the same values and steps on both sides axis by axis, a verdict from `concepts.USE_WHEN`, and a recap from `COMPARE_DIFF`;
  - misconception: `premise_sentence`;
  - "why is X slow": the problem is shown on X (`NEGATIVE_WHY`).
  - A scene may only run on another structure if its requirement names it.
- **Gate:** `answer.shape_problems` checks list items named in their own scenes and restated in the recap, both comparison sides plus a verdict, and a plain premise verdict. The safety net adds only real point sentences (never glued notes) and builds verdict and premise scenes in code. `result["answer_check"]` drives the "Answers your question" chip.
- **New real structures and views:** `array_2d`, `dyn_array` (a static array refuses when full; a dynamic one doubles and copies, with the counts), `jagged_array`, a `variant` op (linked list singly/doubly/circular; queue simple/circular/priority/deque, with real priority and deque behaviour), and `reset`. The frontend stage has grid, dynamic and jagged views and draws the variants.
- **Export:** keyframe capture (`render-view.tsx` `__renderPlan`/`__renderGoto`, Motion's `skipAnimations` for jumps), 4 async Playwright workers, and held frames with the ffmpeg concat demuxer. Before: real-time capture, about 68 s for a 57 s video (the user saw 95 s for 58 s). After: 6 to 8 s for 48 to 84 s videos (9 to 15%). Background prefetch, join, cancel, and a cache keyed by lesson id + hash.
- **Tests:** `tests/test_question_shapes.py` (15 shapes, the root-cause regression, unsupported, vague). Eval: `eval_lessons.py --shapes` (BEFORE from `eval_before_shapes.json`): 15 of 15 live.
- **Rough edges:**
  - the LLM's comparison narration is sometimes stilted ("A row of lockers numbered from 0, so you can walk straight to any locker, places 45 at slot 1");
  - a "why" lesson can include a weakly related cause demo (a `get`);
  - the judge's verdict is taken before repairs, by design, to stay at 3 calls.

## Earlier status (2026-11-22)

**Revision honesty, beginner clarity additions, video export: done.**
- **Revision bug:** "explain step 2 in simpler words for a beginner" reported "rewritten" with identical text. Cause: both LLM rewrites failed verification (wrong analogy, missing values), so the verifier fell back to the scene's template, which was the old text. Now `revision.py` verifies the candidate itself, retries once with the reasons, refuses honestly, splices only the revised scene, and returns `before`/`after` (the generator shows them). Live: a "simpler for a beginner" revision of BST step 2 now returns new verified text (7.2 s to 4.5 s) with the same ops and state, other scenes byte-identical.
- **Clarity additions:**
  - `clarity.repeated_word` (also checked in `verifier.check_scene` at every level) and `clarity.named_parts` (root, leaf, head or tail named on a scene that does not show one is flagged; shown parts go to `scene.named` for the stage highlight);
  - `lesson.trim_repeats` (a name is said once, a sentence already said word for word is dropped, each trimmed scene re-verified);
  - BFS template never says "start at A, then visit A";
  - the graph analogy is now a map of places and roads;
  - quiz distractors replaced where silly;
  - the missing key-term safety net uses `concepts.name_sentence` (never "This is about the BFS."), and "breadth first search" counts as "BFS".
- **Video export:** see `video.py`, `components/render-view.tsx`, `components/video-export.tsx`. ffmpeg 9.1 was installed with winget for this user. Live: the BST lesson is a 57.1 s MP4 and the BFS lesson 62.0 s (1280x720, H.264 + AAC, video and audio within 0.02 s), each exported in about 65 to 70 s; a repeat download comes from the cache in 0.1 s.
- **Tests:** `tests/test_export.py` (unit, ffmpeg-only and an end-to-end export of a small Piper lesson that skips without the frontend), revision honesty tests in `tests/test_quiz_revision.py`, BST and BFS goldens in `tests/test_clarity.py`.

## Earlier status (2026-11-20)

**Beginner clarity: done.** Lessons answered the question but suited only people who already knew data structures. Problems found: a 17.7 s jargon scene, definitions made of more jargon, FIFO before any picture, garbled glosses, an analogy that vanished after scene 1, marketing in place of the "why", and a duplicate cyan caption. Changes:
- **Level:** `build_lesson` stores `level` in `plan.analysis`. Beginner lessons get `ctx["beginner"]`. Intermediate lessons, and lessons saved before this change, keep the old checks.
- **Prompts:** the plan, repair and judge prompts carry the BEGINNER STYLE GUIDE (`answer.style_guide`), which covers the analogies, the glossary for the guessed subject, picture first, problem before fix, and no filler.
- **Verification** (inside `verify_scenes`, still one repair round):
  - clarity flags join `lesson_errors`;
  - then `define_first` runs, with no LLM call;
  - then the template fallback, which uses the plain templates in beginner mode.
- **After verification:**
  - explanation scenes with no ops that run over 2 sentences are split into one-idea scenes (`lesson.split_scenes`), each part verified;
  - scenes using the analogy get `analogy` (its tag), and the frontend shows it as a small chip.
- **Judge:** the clarity judge ("would a 12-year-old who has never coded understand each sentence?") rides on the existing judge call. Its fixes are accepted only if they verify, are clear, and drop no part of the answer; otherwise the old text stays. When a judge fix for an uncovered requirement fails on a demo scene, the plain template is used and the point follows in its own short scene.
- **WHY questions** (`answer.add_why_scenes`) show the problem first on the alternative, with real ops, then the fix on the subject. Gemini's own scenes are used when their ops really show it; a scene Gemini labelled "problem" or "fix" with the wrong ops gets the real ops.
- **Key terms** are limited to words in the question ("O(" is also allowed for complexity questions).
- **Frontend:** the duplicate answer-point line is removed; one larger caption, plus the analogy chip.
- **Tests:** `tests/test_clarity.py` (29 tests): golden lessons for linked list why, queue, stack and array, starting from bad plans with a repair call that fixes nothing; one test per real-world problem; the 7 varied questions stay short. 216 tests pass in total.
- **Eval:** `eval_lessons.py --clarity` prints BEFORE (`eval_before_clarity.json`) and AFTER narration per scene, with words per sentence and flags. Live on 2026-11-20: 4 of 4 PASS, 3 LLM calls each, 4–6 s for a new lesson.
- **Known rough edges:**
  - the template fallback can repeat a second sentence across similar scenes ("Every locker has a number, so no searching is needed.");
  - Gemini sometimes chooses odd demo ops (searching for the first box);
  - complexity lessons built by code (`complexity.py`) are not yet rewritten for beginners.

**Question-driven pipeline: done.** New lessons no longer go through a fixed intent list. `lesson.build_lesson` runs `answer.py`, which makes at most 3 LLM calls:
1. **One call for analysis and plan** (`answer.analyze_and_plan`). It returns:
   - the subject and the question restated (`ask`);
   - 3–6 `requirements`, each with its evidence: trace, count, table, compare, state or none;
   - `key_terms`, and `jargon` with plain-words definitions;
   - answer points (one per requirement);
   - scenes (one point each).
2. **Code normalisation** (`answer.build_plan`), which is generic:
   - unmapped scenes are dropped, except a short intro or recap;
   - impossible ops are cut;
   - missing evidence is built by `evidence_scenes`, using the lesson's own values;
   - every sort or graph run is completed, run by run (`_finish_runs`);
   - runs of the same sort use the same n.
3. **Verification:** the verifier checks every sentence, then one batched repair call fixes failures (`verify_all(..., rounds=1)`).
4. **Answer gate** (`lesson.answer_gate`):
   - first the deterministic `answer.gate`: requirements covered, key terms said, no unmapped scene;
   - then one judge call at temperature 0 (`answer.judge`, via `llm.temperature`) that also rewrites the scenes of uncovered requirements;
   - a rewrite that fails verification falls back to the scene's template, which only counts as a repair if it states the requirement's point;
   - if the lesson still fails: a counted-evidence lesson (`complexity.py`, no LLM call) when the algorithm is countable, else `answer.NotAnswered`. The API returns that as `not_answered`, and the frontend shows the honest message.
- **Fallback:** if the analysis call fails or is unusable, the same response feeds the older focus pipeline (`planner.make_plan(first_raw=...)`), so it costs no extra call.
- **New structures:** `insertion_sort` (InsertionSort) and `graph_dfs` (GraphDFS, a stack), with counters.
- **Verifier additions:**
  - `generic_lesson_errors`: demo scenes must say what they show; LLM jargon is explained at first use; a Big-O claim needs a derivation;
  - `strip_formulas`: digits in "n − 1" or "n(n − 1)/2" are algebra, not claims;
  - `generic_template`;
  - counted claims are checked in any lesson (`complexity.infer_algo`).
- **Quiz** (`quiz.question_questions`): a core-point question first, from the lesson's evidence, then computed questions on its own steps. No LLM rewording call.
- **Frontend:** DFS and insertion sort stages, the current answer point shown above the subtitles, and the `not_answered` message.
- **Tests:** `tests/test_question_driven.py` holds property tests for 12 varied questions, with a deliberately weak fake LLM. 187 tests pass in total.
- **Eval:** `eval_lessons.py --questions` runs the 12 live and prints requirements, covering scenes, the judge verdict and the narration. `--before-after` shows your 3 questions against `eval_before.json`. On 2026-11-20 all 12 passed live, with 3 LLM calls each and 5–30 s per new lesson (instant when cached). Linear search and bubble sort complexity sometimes use the counted-evidence fallback after the judge rejects the generic answer.
- The old named CASES/CHECKS in the eval describe the focus pipeline, which is now only the fallback, so live they no longer match the main path.

**Complexity intent: done.** "What is the time complexity of bubble sort" used to produce a "how does it work" lesson. Now:
- `focus.analyze` detects complexity questions (`complexity.COMPLEXITY_WORDS`) and sets `intent="complexity"` and `algorithm`. Supported algorithms are bubble sort, linear search, linked list search, BFS, stack push/pop, queue enqueue/dequeue, array access and linked list insert at the head. Anything else, such as insertion sort or DFS, gets an honest "not supported yet" message.
- `complexity.py` builds the whole lesson in code, with **no LLM call**. Its scenes are goal, measure, a demo run to completion (one scene per pass or BFS level, with a live counter), derive (`3 + 2 + 1 = 6 = n(n - 1) / 2`), Big-O in plain words, a growth table (n = 4, 8, 16, 100), best and worst case both run for real, and the recap.
- `structures.py` holds the counting code: `run_bubble`, `run_scan`, `run_list_search`, `run_bfs`, `count_work`, and the `growth` structure. Bubble sort tracks comparisons and passes, arrays have a one-comparison `scan`, BFS counts visits and checks, and `touched` is recorded for O(1) ops.
- The verifier (`complexity_errors`) checks counts, sums, formula values, table rows, doubling ratios and Big-O against the real runs. A scene that runs the algorithm may only state that run's counts.
- The answer-coverage gate checks `ctx["must_cover"]`, both in `lesson_errors` and in `lesson.ensure_answer`. `spoken()` reads math aloud in words ("O of n squared").
- The quiz (`quiz.complexity_questions`) is computed by code: the worst-case count for 5 items, the effect of doubling the input, and the best case.
- Frontend: `WorkMeter` (live counter and per-pass tally), `GrowthStage` (table with log bars), and the array scan highlight.
- `tests/test_complexity.py` adds 43 tests, so 170 pass in total. Live eval: the 3 complexity cases plus all 8 older cases PASS. Complexity lessons take 90 to 136 s to play and about 3 s to generate.

**Answer-first redesign: done.**
- The planner outputs `answer_points` first, then scenes with a `point_id`. `focus.assign_points` gives every scene exactly one point; only the demo spans several scenes.
- "What is" lessons use the outline definition, analogy, rule, demo (proves the rule), uses, recap.
- `verifier.lesson_errors` checks the whole lesson: jargon explained before use, the rule stated in a demo scene, and a recap that neither re-defines the structure nor overlaps the intro by more than 0.5. Point kinds are checked per scene.
- The quiz has a principle question, a real-world or vocabulary question, and a short trace (`quiz.what_is_questions`).
- A "what is" plan with an invalid op keeps Gemini's text, because the demo is rebuilt in code (`planner._salvage_what_is`).
- `tests/test_answer.py` holds the golden cases. Live eval on 2026-11-20: what is stack, queue, linked list and array, the delete case and the BFS case all PASS.
- 127 tests pass.
- Fixed along the way:
  - "binary search tree" was read as the verb "search";
  - "on top of 12" was read as the claim "the top is 12";
  - the scene cache key was missing the point kind;
  - `init` now accepts a single value.

### Earlier status (2026-11-19)

**Done**
- Everything before the focus rewrite:
  - lessons, verifier v2, quiz from the lesson, revision and TTS;
  - auth, MongoDB, dashboard, saved lessons and profile;
  - UI upgrade;
  - Gemini reliability.
- Lenis has been removed (native scrolling); offscreen animations pause.
- **The focus rewrite is complete:**
  - Backend: question analysis (`focus.py`), roles, shaping, linked list `init`/`walk`/`insert_after` with pointer details, pointer-aware verifier, focus concepts and the 50% core budget, focused quiz, `eval_lessons.py` (`--before`, `--save`, `--only`, `--full`).
  - Frontend: new fields in `lib/types.ts`. The linked list stage highlights the `current` node and the rewired pointer (accent arrow, "prev" label). New `opCaption`s, and a role chip in the player.
  - Saved lessons keep `role`, `structure` and `analysis`: `plan` and `snapshot` are Mixed in Mongoose, zod uses `looseObject`, and revise sends `lesson.plan` back unchanged.
  - The README is updated.
- **Tests:** 107 pytest tests pass. `npx tsc --noEmit` and lint on the changed files are clean.
- **Live eval** (2026-11-19): all 6 golden cases PASS, with core share 50–61% and 2 setup scenes each. The comparison now works; before, it failed as unsupported. The BEFORE snapshot is in the session scratchpad (`before.json`), which is temporary.
- The backend runs without `--reload` on port 8000; the frontend is on 3001.

**Possible follow-ups (not requested yet)**
- Delete lessons run long (about 86 s), because every focus detail sentence and every edge case is added. Merging the edge cases sooner, or capping the number of detail sentences, would shorten them.
- Gemini sometimes adds a "like a treasure hunt" analogy to `how_op` setup scenes. It is harmless and verified, but could be discouraged.
- Browser-check the new linked list stage visuals (walk highlight, rewired arrow) with Playwright.

## Open issues

- **Lessons take about 32 s to generate.** Planned speed-ups:
  - synthesize Piper audio for scenes in parallel;
  - set the Gemini thinking budget to 0;
  - a progress UI showing the stages (planning, verifying, voicing).
- **Scroll smoothness:** Lenis has been removed in favour of native scrolling, and a Playwright check measured wheel input settling in about 60 ms. Confirm with the user that it feels right.
- **Gemini 503 handling:** fallback, backoff and the friendly busy UI are in place. Keep watching for persistent `ai_busy` errors.

## Deployment (2026-11-25)

- **Frontend:** Vercel project `structura`, live at https://structura-gules.vercel.app. It deploys from `frontend/` with `vercel deploy --prod`; `frontend/vercel.json` sets the Next.js framework (without it every page was a 404).
- **Vercel production env:** `MONGODB_URI`, `AUTH_SECRET`, `NEXT_PUBLIC_API_URL=/api/backend`, `BACKEND_URL`.
- **Backend:** runs on the laptop (`uvicorn main:app` on port 8000), exposed by ngrok on a SECOND ngrok account, with its own config file at `%LOCALAPPDATA%\ngrok\structura.yml` (web UI on port 4041). Start it with `ngrok http 8000 --config "%LOCALAPPDATA%\ngrok\structura.yml"`. Its fixed domain is `rut-glamour-nanometer.ngrok-free.dev` (= `BACKEND_URL`).
  - The default ngrok account and its domain belong to the FYP actor-coach app on port 8001. Do not stop that tunnel.
- **Proxy:** `frontend/app/api/backend/[...path]/route.ts` forwards to `BACKEND_URL` with `ngrok-skip-browser-warning`, so the browser never sees the tunnel.
- **Export:** `backend/.env` `FRONTEND_ORIGINS` lists the Vercel site, so it may request video exports; the render page fetches the lesson through `api_base` (the proxy).
- **Atlas** accepts Vercel: a live signup, login and dashboard check passed.
- **New lessons** need the laptop, the backend and the tunnel all running.

## Gotchas

- Edit scripts that pass `\b` through Python heredocs can write backspace characters into files, so grep for `\x08` after scripted edits. Prefer the Write and Edit tools, or a script file written with the Write tool.
- Git Bash's `/tmp` is not visible to the Windows Python; use the session scratchpad instead.
- Under `cacheComponents`, call `await connection()` before Auth.js `auth()`, and keep session reads inside `<Suspense>`.
- Some networks never answer DNS **TXT** queries. A `mongodb+srv://` URI then hangs for about 95 s on every cold connect (`queryTxt ETIMEOUT`), and logged-in pages sit on skeletons. `lib/db.ts` works around this: it resolves SRV itself, tries TXT with a 3 s timeout, and connects with a plain `mongodb://host1,host2,host3` URI. Do not revert to passing the SRV URI straight to `mongoose.connect`.
- A new TLS connection to Atlas takes about 3.7 s from this machine. `instrumentation.ts` opens the connection at server start, and `lib/db.ts` keeps `minPoolSize: 4` open and must NOT set `maxIdleTimeMS`, which made requests wait for new sockets (2–6 s loads). Network blips (18 s loads, then "could not load") are handled by a 5 s heartbeat, `socketTimeoutMS`, a single retry of every read in `lib/data.ts` (`read()`), and the dashboard's `RetryNotice`, which re-fetches by itself.
- The lesson schema needs `minimize: false`. Mongoose's default deletes empty objects, such as a state's `last: {}`, which made saved lessons crash the stage. `Stage` also tolerates a missing `last`, so lessons saved earlier still open.
- `next/dynamic` must only be called from Client Components (see `components/landing/lazy-sections.tsx`).
- The repo is public at https://github.com/Saroash3/structura. Commit and push only when the user asks.
