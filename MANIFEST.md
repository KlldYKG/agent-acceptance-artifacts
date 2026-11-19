# Artifact Manifest

Snapshot date: 2026-11-19. Tool version used in all runs: agent-acceptance
v1.0.0 (experiment lock; the released v1.0.1 adds `--phase-timeout` and
mutation-backend hardening, with no change to evaluation semantics).

## dataset/

| File/Dir | Provenance |
|---|---|
| `gold/` | Task chains A–E: 30 tasks total (A 8, B 11, C 10, D 11, E 10)… author scaffolds in `gold/authored/`, dogfood replicas in `gold/dogfood_*`; per-chain gold reports `report_[A-D].json` |
| `gold_check.py` | Bidirectional-validity checker used offline (fail-before → pass-after) |
| `quality_check.py` | Pilot quality scorer |
| `run_chain.py` | Dataset-side chain scaffolding helper |
| `HARNESS_GUIDE_CN.md` | Environment layout and venv conventions |
| `GOLD_VALIDATION_CN.md` | Gold-test validation methodology |
| `PILOT_QUALITY_REPORT_CN.md` | Pilot-run quality report |
| `REPO_SCREENING_CN.md` | How the 6 target repos were screened |
| `TASK_CHAINS_DRAFT_CN.md` | Chain design notes |
| `quality_report/` | Machine-readable pilot outputs |
| `REPOS.md` | Pinned upstream commits (clone instead of vendoring) |

Excluded from this package on purpose: `dataset/repos/` (55 MB of clones,
replaceable via `REPOS.md` pins) and `dataset/venvs/` (291 MB of per-task
virtual environments, rebuildable per `HARNESS_GUIDE_CN.md`).

## harness/

| File | Role |
|---|---|
| `runner.py` | Chain runner: drives agent rounds, gate invocation, cost capture |
| `adapters.py` | aider / opencode CLI adapters (process-group kill, platform quirks) |
| `exp_common.py` | Shared paths, run-dir creation, cost parsing |
| `collusion_check.py` | Same-source collusion contrast (A1 vs A-full) checker |
| `vround_check.py` | V-round validation driver (false-positive / determinism / adversarial suites) |
| `make_figures.py` / `make_figures_rq3.py` | Regenerate `figures/*.png` |

Note: batch launcher scripts (`worker_s3*.sh`) and the cloud `env.sh` live on
the execution server; they contain no logic beyond loops over task lists and
`export DEEPSEEK_API_KEY=<redacted>`, and are omitted to keep the package
free of any credential-bearing file.

## runs/ (two-tier release)

- **This GitHub repository** carries 7 representative A0-era runs (63 tasks, 84
  gate rounds) for browsing: aider/opencode flash A0 runs plus the v4-pro C run.
- **The Zenodo archive** (`aa_runs_full.tar.gz`, 51 MB) contains the complete
  set: 46 runs / 468 task instances — the A0 baseline arm (5 chains × 3 repeats
  × 2 adapters = 300 task instances), the 6 A1 intervention runs on the C/D
  chains, the v4-pro model-tier runs, and the RQ3 ablation runs. The superseded
  pre-fix mutation archive (`_oldmut_afull`) is excluded and documented in
  `analysis/RQ3_ABLATION_CN.md`.

| Directory | Contents |
|---|---|
| `aider-deepseek-deepseek-flash-A0-A-r0` / `-C-r0` / `-D-r0` | RQ1/RQ2 flash A0 runs (chains A, C, D) |
| `opencode-deepseek-deepseek-flash-A0-A-r0` / `-A-r1` / `-C-r0` | opencode flash A0 runs (chain A rerun 1, rerun 2, chain C) |
| `opencode-deepseek-deepseek-v4-pro-A0-C-r0` | v4-pro strong-model baseline (chain C) |

Per run: `chain_log.json` (authoritative per-round verdicts + usage costs),
`meta.json`, per-task `transcript_r*.txt/log`, `diff.patch`, `gold_result.json`.
A-full and RQ3 mutation-phase raw outputs were produced on the Linux execution
server and are included in the Zenodo archive with the same schema; the
ablation report (`analysis/RQ3_ABLATION_CN.md`) documents which local runs were
superseded.

## figures/

`rq1_decay_curves.png`, `rq2_intervention_effect.png`, `rq3_ablation.png` —
identical to the paper's Figure 1–3 sources.

## analysis/

Chinese-language working reports kept verbatim as the analysis-of-record:
RQ1 flash decay, RQ2 A1 intervention effect, RQ3 ablation, V-round validation
(false-positive 0/43, determinism, adversarial A/B/B2/C), collusion contrast,
cost calibration, experiment design; plus the three batch launcher stdout logs.

## Integrity

- Secrets scan (2026-11-19): zero matches across all published files.
- Tool repo at v1.0.1: https://github.com/KlldYKG/agent-acceptance
- Zenodo DOI (dataset archive): [ZENODO-DOI]
