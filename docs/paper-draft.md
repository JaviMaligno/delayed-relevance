# The Runtime Is Not Infrastructure: A Replication of SKILL.state

**Draft.** Every figure comes from a measurement in this repository, with per-step
traces and raw data on the `runs/table1-gemini-3-flash-preview-vertex` branch.

---

## 1. What the paper claims, and what we measured

[SKILL.state](https://arxiv.org/abs/2608.26263) argues that an agent maintaining
**explicit state** executes long procedures far better than one carrying the whole
conversation, and that the gap widens with the horizon. Its Table 1 shows this with
Gemini-3-Flash in a simulated warehouse: ReAct falls from 0.90 to 0.74 between 10 and
200 steps while SKILL.state holds at 0.94.

We reimplemented their environment from the paper's description — SkillExecBench is not
public — and measured three things:

1. **Whether the ladder reproduces** under their own model and decoding settings (§3).
2. **What each runtime actually costs** when you count money rather than tokens (§4).
3. **What explicit state protects against**, through two probes aimed at the
   limitations the paper itself declares but does not measure (§5).

The short version: **their thesis holds, their ordering nearly holds, their magnitude
does not, and their cost accounting inverts once you bill it**. And the largest effects
in the whole experiment come not from any of the compared methods, but from runtime
implementation decisions the paper treats as neutral.

---

## 2. Environment fidelity, and the differences we declare

The paper publishes the environment design (Appendix B.1), the generator pseudocode
(Algorithm 2) and the prompts (Appendix A), so the comparison is not blind.

**What matches**: 500 single-occupancy shelves, the action space
(`Store`/`Ship`/`Move`/`Wait`), item destruction on `Ship`, the metric (valid actions
executed / actionable events) and per-seed determinism.

**What did not match, and is now closed behind flags** (`--apendice-b`,
`--sin-telemetria`):

| Difference | What we did |
|---|---|
| No maintenance events, so `Move` was never exercised | Implemented: 6–11 per 50-step episode |
| Invalid actions were applied rather than rejected | Rejection with a local error observation, as in their B.1 |
| A third of our steps were non-actionable telemetry | Removed: their Algorithm 2 has no non-actionable family |

**Closing all three changes nothing.** ReAct at T=200, same output cap, 15 runs per
condition: 0.905 ± 0.070 in the original environment and 0.913 ± 0.072 in the corrected
one. Difference +0.008, **0.3 standard errors**.

**Differences that remain, declared**:

- **Our actions carry four fields** (`shelf`, `sku`, `units`, `lot`) against their
  positional two. There is more to get right per action, which cuts against the
  "our environment is easier" hypothesis. The failure adjudication (§6) quantifies it
  at 16 %.
- **Our observations are more verbose.** The match is by **context density**, not
  literal content. At T=200, ReAct's mean prompt is 58,127 tokens against their 48,007
  — **above theirs**.
- **Which empty shelf their ground truth picks in `Store`** is unspecified. We take the
  lowest-numbered free shelf. This is the one difference that requires asking the
  authors.

---

## 3. The capability ladder

Faithful environment, `gemini-3-flash-preview` via Vertex, `temperature=0`, `top_p=1`
(their settings), **15 runs per cell** (5 seeds × 3 repetitions), 304 episodes with
per-step traces. Their Table 1 in parentheses.

| T | ReAct | Memory | Stateful | SKILL.state |
|---|---|---|---|---|
| 10 | 0.993 ± 0.026 (0.90) | 1.000 ± 0.000 (1.00) | 1.000 ± 0.000 (1.00) | 1.000 ± 0.000 (1.00) |
| 25 | 0.955 ± 0.050 (0.92) | 0.987 ± 0.042 (0.99) | 1.000 ± 0.000 (1.00) | 1.000 ± 0.000 (1.00) |
| 50 | 0.936 ± 0.057 (0.88) | 0.953 ± 0.077 (0.93) | 0.996 ± 0.008 (0.94) | 1.000 ± 0.000 (0.96) |
| 100 | 0.960 ± 0.063 (0.84) | 0.839 ± 0.096 (0.87) | 0.995 ± 0.008 (0.91) | 1.000 ± 0.000 (0.94) |
| 200 | 0.913 ± 0.072 (0.74) | 0.810 ± 0.083 (0.84) | 0.912 ± 0.126 (0.88) | 1.000 ± 0.000 (0.94) |

Drop from T=10 to T=200 (ours / theirs): ReAct −0.080/−0.160 · Memory −0.190/−0.160 ·
Stateful −0.088/−0.120 · **SKILL.state 0.000/−0.060**.

**What reproduces.** Their central thesis, with room to spare: SKILL.state does not fail
**once in 75 episodes** of up to 200 steps. It is the only arm with zero degradation;
theirs loses six points. The overall ordering reproduces too — both explicit-state
runtimes above both text-reconstruction ones.

**What does not.** The magnitude: every arm of ours degrades roughly half as much. At
T=200 our ReAct sits **17 points above** theirs, and the gap widens with the horizon
(+0.09 at T=10, +0.17 at T=200). It is not explained by the model (it is theirs), by
reasoning effort (measured across two orders of magnitude, §6), by the output cap, or
by any of the three environment gaps.

**Where their ordering breaks.** Memory comes last in our environment; they place it
above ReAct. **This is a difference of ours, not a finding**: our summariser compresses
to a 5,874-token mean prompt at T=200 where theirs occupies 84,364. Their
"Memory (Summary)" barely summarises; it retains almost as much context as ReAct.

### Dense noise (their Experiment 2)

T=50 fixed, distractors appended to the observation under their header, 15 runs per
level:

| Noise (events/turn) | Our ReAct | Theirs |
|---|---|---|
| 0 | 0.961 ± 0.037 | 0.88 |
| 5 | 0.952 ± 0.066 | 0.68 |
| 20 | 0.959 ± 0.056 | 0.61 |
| 50 | 0.859 ± 0.121 | 0.53 |

From 0 to 50 events: **−0.103, 3.1 standard errors**. Theirs: −0.350. **The effect is
real but not gradual**: 0, 5 and 20 are the same number; all of it is in the jump to 50.
And what changes most is not the mean but the dispersion, which triples: under 50
distractors the model is not stably worse — it is **erratic**.

---

## 4. Cost accounting with caching

The paper compares **tokens**; whoever pays the bill compares **money**. An append-only
transcript caches almost entirely; a mutating state block invalidates the prefix.

Measured on Anthropic (Haiku 4.5, T=50, 3 seeds, caching on):

| Runtime | Score | Raw tokens | Effective cost | Cache saving |
|---|---|---|---|---|
| ReAct | 1.00 | 826k | **152k** | **82 %** |
| Stateful | 1.00 | 873k | 873k | 0 % |
| Memory | 0.87 | 313k | 313k | 0 % |
| SKILL.state | 1.00 | **109k** | 109k | 0 % |

**SKILL.state's advantage goes from 7.54x in tokens to 1.39x on the invoice**, and the
ordering inverts: by tokens SKILL.state < Memory < ReAct < Stateful; by money
SKILL.state < **ReAct** < Memory < Stateful.

Three consequences:

1. **Compressing context and caching context are in conflict.** Every method that
   compresses rewrites the prefix, and rewriting the prefix kills the cache.
2. **Prompt order is a first-order cost variable.** ReAct and Stateful send nearly the
   same content; ReAct puts history first and saves 82 %, Stateful puts it after a
   mutating state block and saves 0 %. **The same content, in a different order, costs
   5.7x more** — and their Appendix A.3 template places it in the worse position.
3. **It reconciles an anomaly in their table.** Their totals column sits ~3.5x below
   horizon × mean prompt at every horizon. With caching it fits: their totals would be
   billed, their mean prompt raw.

### And it does not transfer across providers

Measured on Vertex with `gemini-3-flash-preview`:

- **There is no implicit cache.** Four identical calls with a 20,016-token prefix, and
  the `cachedContentTokenCount` field **does not even appear** in the response.
- **Explicit caching works** — 20,013 of 20,016 tokens discounted — but **is useless for
  ReAct**: its prefix grows every step, so you would have to recreate the cache object
  each turn, paying the write, to cache something that will not recur. It fits a
  **fixed** large block: the profile of a long procedure, not of accumulated history.

Resulting statement, stronger than the initial one: **explicit state's cost advantage
does not depend on caching; the provider only changes how much it disguises it.**

---

## 5. Two probes on their declared limitations

The paper declares two limitations without measuring them. We measured them.

### L1: explicit state only protects what was anticipated

A fact arrives at step `t` and changes the correct action at `t+40`. Sonnet 5, **same
seed × 8 repetitions**, each seed its own control:

| Condition | Accuracy on the dependent step | 95 % CI |
|---|---|---|
| No field to store it | 12 % (3/24) | 4–31 % |
| Free-form `notes` field | 21 % (5/24) | 9–40 % |
| Schema field naming the fact | **75 %** (18/24) | 55–88 % |
| Reminder attached to the observation | **83 %** (20/24) | 64–93 % |

The conditions split into two groups that do not overlap. **Giving it somewhere to go is
not enough: the somewhere has to say what to store.** An explicit-state runtime protects
against what its designer already anticipated — precisely limitation L1, now with a
number.

> This measurement **withdrew** an earlier recommendation of the project itself. With
> one run per seed, the free-form field scored 60 % and had become the practical advice
> ("leave a hatch in your schema"). With repetitions it is false.

### L2: retroactive invalidation

An announced fact stops being true later. Counted over **dependent steps**, not
episodes:

| Model | Runtime | Applies the correction |
|---|---|---|
| Haiku 4.5 | ReAct | 3/44 — 6.8 % |
| Haiku 4.5 | SKILL.state | **44/44 — 100 %** |
| Sonnet 5 | ReAct | 15/38 — 39.5 % |
| Sonnet 5 | SKILL.state | **49/49 — 100 %** |

**Explicit state does not fail once: 93 of 93.** Full history gets 18 of 82. And ReAct's
failure is all-or-nothing per scenario: in Haiku it misses all 11 dependent steps of one
episode, all 7 of another, all 4 of a third. This is not an agent that slips; it is a
flawless agent that **never updated a fact**.

**Declared scope**: both probes are measured on Claude (Haiku 4.5 and Sonnet 5), not on
Gemini. Replicating them on the third model is pending.

---

## 6. Instrument and artefacts

This is the section that separates this from a blog post, and the one that cost us most.

**Nine artefacts catalogued** in the first block, all with the same signature: an
implicit contract between runtime and model. The runtime assumed something it never
declared, and the result depended on whether the model guessed right. The first three
cost entire grids; **two surfaced in the audit before publication, and both had produced
a written result, with tables and intervals, ready to send**.

This second block added four more, and they are worth enumerating because they transfer:

1. **Greedy decoding does not guarantee reproducibility.** The protocol assumed that at
   `temperature=0` seeds are environment instances and one run per cell suffices. The
   same cell repeated five times gives between 0.830 and 0.960. **Three already-written
   conclusions collapsed on repetition**: an environment effect of −5.8 points that
   turned out to be +0.008, a "monotonic" noise curve that turned out flat, and a
   noise estimate of eleven points that turned out to be a tail.
2. **The distribution has a left tail because failures cascade.** Ordinary run-to-run
   noise is 0.006 (T=100) to 0.012 (T=200), but a single run can land at 0.83. What
   forces repetition is not the noise: it is the tails.
3. **The runner discarded the model's responses.** It kept the score and the token
   counts, so `correct=False` was an indistinguishable zero: you could not tell whether
   the model lost track of state — what the experiment measures — or miscopied a JSON
   field. With responses retained, adjudicating 45 failures gives **30 state errors
   (67 %), 7 wrong actions, 7 copy errors (16 %), 1 unparseable**.
4. **A truncated episode counted as complete.** Aggregation counted files, not steps; an
   episode of 163 steps out of 200 entered the mean. The bias was two thousandths, but
   it was only found because completeness was checked as a matter of routine.

Why traces matter, verbatim from one episode: at step 12 the model stores the SKU of a
different pallet; at step 16 it asserts *"Shelf 0 (SKU-F, stored in step 12)"* when it
had itself stored SKU-B there. **The early error contaminates later decisions** — and
that, not sampling noise, is what produces the tail.

**The transferable claim**: the paper treats the runtime as neutral infrastructure — a
merge operator, a patch format, a schema, a prompt order — when each of those
undocumented decisions is worth between 20 and 90 points, **more than the difference
between the methods it compares**.

**Repository artefacts**: environment with fidelity flags, per-step traces, completeness
verifier, a density meter that does not call the API, truncation counters, per-episode
checkpointing and end-to-end cache accounting.

---

## 7. Limitations

- **`gemini-3-flash-preview` may not be their `Gemini-3-Flash`.** Declared as a risk
  from the outset; the responding model ID is recorded on every run.
- **A reimplemented environment is not their environment.** We matched what their
  appendix allows us to compare, and the remaining differences are in §2. The shelf
  choice in `Store` still awaits an answer from the authors.
- **Our Memory is not comparable to theirs.** Our summariser compresses five times more.
  What we measured is our summarisation policy, not "summarisation" as a category.
- **We have not proven the environment gaps have no effect**; we measured that, at the
  power available, none above ~5 points is detectable.
- **The probes are measured on Claude, not Gemini.**
- **One environment.** The second (Software Repository) was retired: it did not
  discriminate between runtimes and would have added noise without information.
- **SKILL.state at 1.000 with zero variance also means the task does not discriminate at
  the top.** That it never fails does not prove it is infallible: it proves that here
  the ceiling is the ceiling.
