# ICAA examination assembly — reproducibility package

Public release branch: **`reproducibility-public`** at [github.com/papudg/Research](https://github.com/papudg/Research/tree/reproducibility-public).

This branch contains only the artifact cited in Section 4.4 of the paper (`updatedICAA_lookahead_12_revised.tex`). The `main` branch may hold additional internal research material not intended for public redistribution.

## Repository layout

```
research/
├── README.md
├── REPRODUCIBILITY.md          # Full regeneration instructions
├── requirements.txt
├── pyproject.toml
├── docs/
│   ├── updatedICAA_lookahead_12_revised.tex
│   └── qbank_audit/
│       └── cbse_class_x_maths_questions_full_updated.json   # 475-item fixture (place here)
├── data/
│   └── manifests/              # Exported seed-42..46 blueprint manifests
├── src/
│   └── icaa/                   # Importable library (solvers, benchmarks, metrics)
├── experiments/                # Runnable harness + paper result artifacts
│   ├── REPRODUCIBILITY.md
│   ├── *.py                    # Experiment runners
│   └── results_*.{json,txt}    # Recorded outputs cited in the paper
└── scripts/
    └── export_manifests.py
```

## Quick start

1. Place the 475-record item bank at `docs/qbank_audit/cbse_class_x_maths_questions_full_updated.json` (see that directory's README).
2. Create a virtual environment and install dependencies:

```powershell
python -m venv .venv-icaa
.\.venv-icaa\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-icaa\Scripts\python.exe -m pip install -e .
.\.venv-icaa\Scripts\python.exe -m spacy download en_core_web_sm
```

3. Export fixed manifests (optional but recommended for byte-identical manifest files):

```powershell
$env:PYTHONHASHSEED='0'
.\.venv-icaa\Scripts\python.exe scripts\export_manifests.py
```

4. Run the sanity check from the repository root:

```powershell
$env:PYTHONHASHSEED='0'
.\.venv-icaa\Scripts\python.exe experiments\generate.py
```

5. Regenerate all paper artifacts — see [REPRODUCIBILITY.md](REPRODUCIBILITY.md).

## Paper mapping

| Paper section | Primary artifacts |
|---------------|-------------------|
| Table 3 (RQ1 core policies) | `experiments/results_revision_suite.json` |
| Table 4 (lookahead diagnostic) | `experiments/results_lookahead_comparison.json` |
| Five-seed robustness (Table 5) | `experiments/results_multiseed_revision.json` |
| RQ2 scaling | `experiments/results_scaling.json` |
| RQ3/RQ4 tightness | `experiments/results_rq3_rq5.txt` |
| B1 pass status audit | `experiments/results_b1_status_audit.json` |
| Joint infeasibility control | `experiments/results_joint_whole_paper.json` |
| Environment record | `experiments/results_environment.json` |

## Access boundary

The controlled-review artifact includes the complete static fixture so reviewers can regenerate reported results. It is not a blanket public-release authorization for question text. A public release must replace question text with metadata-only records unless licensing permits full-text redistribution.
