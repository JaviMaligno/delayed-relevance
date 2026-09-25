You are an adversarial reviewer of docs/paper-draft.md in this repository (a replication of SKILL.state, arXiv 2608.26263). Assume every number may be wrong until you recompute it from the raw artefacts. Do NOT trust the prose or the commit messages.

The seventh review (logs/revision-adversarial-7.log, final section) raised five findings (Sonnet's runtime-dependent exclusions, unmasked instrument summaries, the "no field" arm storing the fact in shelf_contents, the conflated account of L1 versions, and a residual detectability claim in the noise section) and left three earlier ones partial. The author claims to have closed them in commit f5e4954 (git show f5e4954; experiments/resumen_l1.py regenerates results/probeA_*_estricto_v3.json).

Your job:
1. Status of each of those findings: resolved / partially / not, with evidence. Recompute the conditional and joint rates the paper now quotes for Sonnet, and check the regenerated summaries match the traces.
2. A final end-to-end read of the paper: every table and every number quoted in prose, checked against the artefacts at least by spot-check (at least ten figures across all sections); contradictions between sections; stale sentences describing an earlier state of the project; claims stronger than the data; statements about the original paper not supported by its Table 1 (https://arxiv.org/html/2608.26263v1).

Output: status (one line each), then NEW findings most severe first, each with severity (blocker/major/minor), exact sentence, what you checked and how, and the correction. Do not list claims that check out. End with a one-paragraph verdict on whether the draft is ready to publish, and if not, the minimum remaining work.
