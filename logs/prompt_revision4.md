You are an adversarial reviewer of docs/paper-draft.md in this repository (a replication of SKILL.state, arXiv 2608.26263). Assume every number may be wrong until you recompute it from the raw artefacts. Do NOT trust the prose or the commit messages.

A previous review (logs/revision-adversarial-3.log, final section) raised 12 findings. The author claims to have addressed all of them in the commits since 973020b (see git log and git diff 973020b -- docs/paper-draft.md src experiments tests). Your job:

1. For each of the 12 findings, decide whether it is actually resolved, partially resolved, or not resolved, and say why with evidence.
2. Recompute every NEW or CHANGED figure in the paper from the traces:
   - Haiku Stateful with parser v3: results/adj_T{50,200}_claude-haiku-4-5_stateful_s*_g?.jsonl (run_header stateful_parser=3), scores and patches applied.
   - Gemini Stateful v2: *_gemini-3-flash-preview_stateful_s*_f?.jsonl, patches applied.
   - The corrected adjudication (experiments/adjudicar_estado.py) for Haiku SKILL.state T=200 (*_h?.jsonl), Haiku Stateful v3 and Gemini Stateful v2, and the claim that Gemini SKILL.state (headerless *_t?.jsonl, faithful environment: apendice_b and sin_telemetria true) never departs from reality in 75 episodes.
   - The prompt-order experiment: results/adj_T50_claude-haiku-4-5_stateful_s*_{ep,hp}?.jsonl (cache writes now recorded as cache_write). Effective input = uncached + 0.1*read + 1.25*write.
   - The Welch intervals quoted.
3. Check the adjudicator code again for bugs, and check the new Stateful parser v3 and ordering option (src/dr/runtimes/stateful.py) for defects that would bias the measurements.
4. Flag any sentence that claims more than the data supports, any figure mixing conditions, any wrong denominator.

Output: first the status of the 12 prior findings (one line each), then a numbered list of NEW findings, most severe first, each with severity (blocker/major/minor), the exact sentence or cell, what you recomputed and how, and the correct value. Do not list claims that check out. End with a one-paragraph verdict.
