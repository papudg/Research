# Reproducibility manifest

Public repository: [https://github.com/papudg/Research](https://github.com/papudg/Research) (branch **`reproducibility-public`**).

This document supports Section 4.4 (*Reproducibility*) of the ICAA paper. It describes the public artifact only; controlled-review copies may additionally include full question text.

## Artifact contents

| Component | Location |
|-----------|----------|
| Runnable harness | `experiments/*.py` |
| Library source | `src/icaa/` |
| 475-item CBSE Class X Mathematics fixture | `docs/qbank_audit/cbse_class_x_maths_questions_full_updated.json` |
| Fixed blueprint manifests (seeds 42–46) | `data/manifests/manifest_seed{seed}_80.json` |
| Recorded results | `experiments/results_*.{json,txt}` |
| Environment snapshot | `experiments/results_environment.json` |

No runner connects to production systems. Runtime measurements cover CP-SAT model construction and solving only; embedding generation and conflict-graph construction are excluded.

## Dependencies

Pinned versions (recorded in `results_environment.json`):

- Python 3.12.13
- OR-Tools 9.15.6755
- SciPy 1.18.0
- NumPy 2.5.2
- sentence-transformers 5.7.0
- transformers 5.15.0
- PyTorch 2.13.0
- spaCy 3.8.15 with `en_core_web_sm` 3.8.0
- scikit-learn (detector stress test only)

```powershell
python -m venv .venv-icaa
.\.venv-icaa\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-icaa\Scripts\python.exe -m pip install -e .
.\.venv-icaa\Scripts\python.exe -m spacy download en_core_web_sm
```

The duplicate-detector experiment downloads SentenceTransformers `all-MiniLM-L6-v2` via the Hugging Face cache on first run.

## Deterministic settings

- Set `PYTHONHASHSEED=0` before every command.
- CP-SAT: `num_search_workers=1`, `random_seed=1` (30 s cap; lookahead subsolves use 5 s).
- Primary RQ1 manifest: `random.Random(42)`, blueprint IDs 1–80 in order.
- Robustness manifests: seeds 42, 43, 44, 45, 46 (`multiseed_revision.py`).
- RQ3/RQ5 tightness sweep: `random.Random(99)`.
- Scaling synthetic pools: `random.Random(7)`.
- Detector pairs: `random.Random(123)`.

Blueprint generation follows `icaa.multipolicy_benchmark.build_manifest()`:

- Sample 5–7 eligible chapters uniformly from the sorted chapter list.
- Fixed section template A–E: `(K, marks, tier, time)` = `(20,20,1,40), (5,10,2,15), (6,18,3,36), (4,20,5,40), (3,12,4,18)`.
- Difficulty targets: seven uniforms scaled by `(4,5,4,3,2,1,0.3)`, floored, remainder allocated cyclically.
- Bloom targets: rounded 54/24/22 split per section.

Export manifests once after placing the fixture:

```powershell
$env:PYTHONHASHSEED='0'
.\.venv-icaa\Scripts\python.exe scripts\export_manifests.py
```

## Regeneration commands

Run from the repository root unless noted. All outputs land in `experiments/`.

```powershell
$env:PYTHONHASHSEED='0'
$py = ".\.venv-icaa\Scripts\python.exe"

# Environment
& $py experiments\capture_environment.py | Tee-Object experiments\results_environment.txt

# Core evidence (Tables 3–5, joint control, ablations)
& $py experiments\revision_report.py | Tee-Object experiments\results_revision_suite.txt
& $py experiments\multiseed_revision.py | Tee-Object experiments\results_multiseed_revision.txt
& $py experiments\lookahead_comparison.py | Tee-Object experiments\results_lookahead_comparison.txt
& $py experiments\joint_policy_comparison.py | Tee-Object experiments\results_joint_policy_comparison.txt
& $py experiments\joint_diagnostic.py | Tee-Object experiments\results_joint_whole_paper.txt
& $py experiments\b1_status_audit.py | Tee-Object experiments\results_b1_status_audit.txt

# Shared multi-policy suite (legacy B0/BG/B1/B2/B3 denominator)
& $py experiments\multi_policy_report.py | Tee-Object experiments\results_multi_policy.txt

# RQ2 scaling, RQ3/RQ4 tightness, supplementary studies
& $py experiments\scaling.py | Tee-Object experiments\results_scaling.txt
& $py experiments\rq3_rq5.py | Tee-Object experiments\results_rq3_rq5.txt
& $py experiments\baselines.py | Tee-Object experiments\results_baselines.txt
& $py experiments\full_paper.py | Tee-Object experiments\results_fullpaper.txt
& $py experiments\multi_blueprint.py | Tee-Object experiments\results_multi_blueprint.txt
& $py experiments\ablation.py | Tee-Object experiments\results_ablation.txt
& $py experiments\weight_sweep.py | Tee-Object experiments\results_weight_sweep.txt
& $py experiments\weight_sensitivity.py | Tee-Object experiments\results_weight_sensitivity.txt
& $py experiments\policy_frontier.py | Tee-Object experiments\results_policy_frontier.txt
& $py experiments\detector.py | Tee-Object experiments\results_detector.txt

# Sanity check
& $py experiments\generate.py
```

## Policy ↔ code mapping

| Paper symbol | Implementation |
|--------------|----------------|
| $B0$ first-feasible | `icaa.generate.solve_b0` via `evaluate_sequential(..., 'b0')` |
| $B_{LS}$ constructive–local | `evaluate_sequential(..., 'local')` |
| $B1$ sequential lexicographic | `icaa.generate.solve_b1` via `evaluate_sequential(..., 'b1')` |
| $B2$ weighted sum $(1,1,1)$ | `multipolicy_benchmark.evaluate_blueprint(..., 'b2')` |
| $B_C$ direct compliance | `joint_policy_comparison.solve_joint_direct_compliance` |
| $B_J$ joint lexicographic | `joint_policy_comparison.solve_joint_lex` |
| Lookahead $k{=}3$ | `evaluate_sequential(..., 'lookahead')` |

## Key result files

- **`results_revision_suite.json`** — RQ1 Table 3: $B0$, $B_{LS}$, $B1$, $B2$, $B_C$, $B_J$ on 70/80 common-feasible blueprints; paired tests with Holm adjustment.
- **`results_lookahead_comparison.json`** — Table 4: sequential $B1$ vs bounded lookahead.
- **`results_multiseed_revision.json`** — Table 5: seed-level clustered paired analysis (seeds 42–46).
- **`results_scaling.json`** — RQ2 solver runtime vs pool size.
- **`results_rq3_rq5.txt`** — RQ3 tier-wise feasibility; RQ4 soft-compliance pairs.
- **`results_b1_status_audit.json`** — 1,050/1,050 B1 pass statuses on common-feasible RQ1 papers.
- **`results_joint_whole_paper.json`** — Joint-model audit of 10 sequentially excluded blueprints (all `INFEASIBLE`).
- **`results_environment.json`** — CPU, RAM, OS, Python/OR-Tools versions, solver parameters.

## Tests

```powershell
$env:PYTHONHASHSEED='0'
.\.venv-icaa\Scripts\python.exe -m pytest experiments/test_generate.py experiments/test_multipolicy_benchmark.py experiments/test_revision_benchmark.py
```

## Access boundary

The **public** branch ships a metadata-only fixture (ids, marks, time, difficulty, tags) sufficient to rerun all reported solver experiments. Question text is omitted from the public repository. Controlled-review copies may include the complete static fixture for independent verification; that distribution is not a blanket public-release authorization for question text.
