# Issue 002 — a completed generation rendered nothing

**Status: RESOLVED in v0.2.10, guarded in v0.2.11** · Raised 2026-08-10 · Closed 2026-08-10

---

## Symptom

Reported from the form tab: generation ran to completion, then

- the prompt was **gone** — no prompt card, no output;
- the **Generate button stayed greyed out**, so the run could not be retried;
- **no history entry** was written;
- the form inputs were still on screen, so it looked like the work had been discarded.

Nothing appeared in the server log. The generation itself had succeeded.

## Root cause

Two mistakes in the v0.2.8 client-side contract append, both in the same patch:

1. **`applyBaselineContract` was declared inside `applyStatusContract`.** The patch
   anchored on a line inside that function's `for` loop, so the new function landed in its
   body. The top-level call site therefore hit
   `ReferenceError: applyBaselineContract is not defined`.
2. It called **`sectionHeads()`, a helper that does not exist**, and matched `'prompt'` in
   lowercase where the parser emits `'PROMPT'`.

The throw happened *after* the stream completed, in the completion handler, and skipped
the render, the history push and the button re-enable in one go.

**The JavaScript was syntactically valid throughout.** `node --check` would have passed.
A nested function declaration is legal; it is just unreachable from outside.

## Why it surfaced when it did

v0.2.8 shipped the bug **latent**. It only fires when the baseline toggle is on, and in
0.2.8 the toggle was opt-in and off by default.

**v0.2.9's auto-apply turned it from dormant into certain** for `Backend or code` — the
most common work type, and the one the reporting user was about to run.

That is the sharper lesson: a change that makes an existing feature *more likely to be
used* is a change that can expose its latent bugs. It deserves the same testing as a new
feature, not less.

## Resolution — v0.2.10

Both contracts now go through a single top-level helper:

```js
function appendToPromptSection(raw,text){ /* one implementation of the span surgery */ }
function applyStatusContract(raw){return appendToPromptSection(raw,STATUS_CONTRACT)}
function applyBaselineContract(raw){return appendToPromptSection(raw,BASELINE_CONTRACT)}
```

The duplicated span surgery that made the mistake possible is gone.

The call site is now guarded, so this failure mode cannot recur in any form:

```js
try{
  if(wantContract)content=applyStatusContract(content);
  if(wantBaseline)content=applyBaselineContract(content);
}catch(e){lintWarn=(lintWarn?lintWarn+' ':'')+'contract append failed: '+e.message}
```

**A failed append now degrades to "no append", never to "no result".**

## Guard — v0.2.11

Two shipped regressions in two days were invisible to Python syntax checking: a harness
that silently coerced to the wrong value (fixed in 0.2.5), and this one. Neither was
catchable by reading the diff.

`/api/selftest` and a **Run self-test** button on the first tab now run, in-process:

| Check | Catches |
|---|---|
| `test_units.py` | harness coercion, both contract doors |
| `test_logic.py` | every pure function reachable without a network |
| `node --check` on the **served** JS | syntax errors in the page as actually rendered |
| top-level declaration of `applyStatusContract` / `applyBaselineContract` | **this exact bug** — a valid-but-unreachable nested declaration |

The last row exists specifically because syntax checking would not have caught issue 002.
It asserts the property that actually failed: the function must be declared at top level,
where its call site can see it.

Run it before spending a long generation.

**v0.2.13** extended it past the code: the endpoint also confirms the model backend is
reachable, that a pinned model name matches what is actually served, and that a one-token
generation round-trips — reporting `code_ok` and `live_ok` separately.

## Verification

- `run_selftest()` returns 5/5 in-process and over HTTP.
- The contract functions were additionally executed in node against a realistic
  `### PROMPT` payload: both defined at top level, text inserted inside the prompt section,
  `### NOTES` preserved, both contracts ordered correctly, unparseable raw passed through.

## Lesson

The bug was not in logic that anyone reviewed carelessly — it was in *where a function
landed* as a result of a patch anchoring on the wrong line. The defence is not more
careful reading; it is a check that asserts the property the code depends on, run from a
button that costs three seconds before a run that costs ninety minutes.
