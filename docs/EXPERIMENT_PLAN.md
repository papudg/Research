# Beyond Feasibility — Experimental Plan

## 1. Primary objective

The experiments must establish four things without relying on synthetic placeholder results:

1. **Quality:** B1 produces better blueprint-aligned papers than the deployed first-feasible policy B0.
2. **Necessity of optimization:** the improvement is not explained simply by random item ordering or a trivial greedy heuristic.
3. **Practicality:** the quality gain comes at an acceptable computational cost, and the cost is decomposed into similarity construction, model construction, and CP-SAT optimization.
4. **Component validity:** the duplicate detector and compliance formulation contribute measurable improvements.

The main comparison remains **B0 vs B1**. B0-R, greedy, B2, and B3 are supporting comparisons.

---

## 2. Data regimes

### D1 — Production corpus

- 471 CBSE Class X Mathematics items extracted read-only from the deployed platform.
- Preserve the actual metadata distribution.
- Report counts/missingness for marks, time, difficulty, Bloom level, question type, chapter, tags.
- Do not alter the real item metadata except for the explicitly documented integer conversion used by the production baseline.

### D2 — Balanced synthetic corpus

Generate synthetic pools using the empirical schema and distributions of D1, but approximately balance the difficulty bands.

Purpose: determine whether the B0→B1 improvement is merely an artifact of the strongly easy-skewed production bank.

### D3 — Scalability pools

Generate calibrated synthetic banks for:

- 100
- 500
- 1,000
- 5,000
- 10,000 items

Keep metadata distributions, average tags/question, marks distribution, time distribution, and duplicate structure close to D1. Record the random seed for every generated pool.

---

## 3. Blueprint generation

Each blueprint must specify:

- total marks M
- total time W
- number of questions K
- eligible topic set E
- required coverage set R
- target difficulty histogram Delta
- hard compliance rules H
- soft compliance rules S

Generate at least five difficulty/tightness regimes:

### Loose
Large feasible region; many papers should be possible.

### Moderate
Several interacting restrictions.

### Tight
Difficulty, marks, time, topic and structural requirements substantially restrict the feasible set.

### Near-infeasible
Very small feasible region; some instances should remain feasible.

### Infeasible
No feasible solution under the hard constraints. Used only for robustness/feasibility testing.

Important: define tightness quantitatively rather than only by labels. A useful empirical measure is the fraction of generated instances that remain feasible under B0 with the same hard constraints.

---

## 4. Solver methods

### B0 — First feasible

Faithful reproduction of the deployed policy.

- no optimization objective
- fixed candidate order
- same hard constraints
- same conflict graph
- same CP-SAT time limit

### B0-R — Randomized first feasible

Same model as B0, but randomize candidate order over multiple seeds.

Purpose: test whether B0's poor quality is simply an artifact of ordering.

### BG — Greedy heuristic

Construct a feasibility-preserving greedy heuristic that prioritizes immediate improvement in difficulty alignment and coverage.

Purpose: answer the reviewer question: “Could a simple heuristic achieve the same result without CP-SAT optimization?”

### B1 — Proposed lexicographic CP-SAT

Three passes:

1. minimize difficulty deviation D(x)
2. fix D* and maximize required-topic coverage C(x)
3. fix D* and C* and maximize soft blueprint compliance S(x)

Hard compliance remains enforced throughout.

A pass is considered optimal only when CP-SAT returns OPTIMAL. If a time limit prevents proof of optimality, record UNKNOWN/TIMEOUT rather than treating the incumbent as mathematically optimal.

### B2 — Weighted sum

Single-solve scalarization over difficulty deviation, uncovered-topic penalty and soft-compliance penalty.

Sweep a predefined weight grid rather than selecting one convenient weight.

Report both the best weighted-sum result and the sensitivity of the solution to weight selection.

### B3 — Soft-window / goal programming

Use tolerance windows around target difficulty counts with slack penalties.

This represents a common alternative formulation in which targets are treated as acceptable ranges rather than exact optimization objectives.

---

## 5. RQ1 — Does B1 improve paper quality?

### Experimental setup

For each blueprint instance:

- run B0, B0-R, BG, B1, B2 and B3
- use the same item pool
- use the same blueprint
- use the same hard constraints
- use the same conflict graph
- use matched random seeds where applicable

### Primary metrics

1. Difficulty deviation D(x), lower is better.
2. Topic coverage C(x), higher is better.
3. Soft compliance S(x), higher is better.
4. Exact marks satisfaction.
5. Exact time satisfaction.
6. Exact question count.
7. Hard compliance.

### Main statistical comparison

The primary test is B0 vs B1 on matched blueprint instances.

Report:

- median paired difference
- mean paired difference
- 95% confidence interval
- Wilcoxon signed-rank p-value
- effect size

Do not report only p-values.

### Main table

| Method | D↓ | Coverage↑ | Soft compliance↑ | Runtime | Feasibility |
|---|---:|---:|---:|---:|---:|
| B0 | measured | measured | measured | measured | measured |
| B0-R | measured | measured | measured | measured | measured |
| BG | measured | measured | measured | measured | measured |
| B1 | measured | measured | measured | measured | measured |
| B2 | measured | measured | measured | measured | measured |
| B3 | measured | measured | measured | measured | measured |

### Critical additional analysis

Run the same experiment separately on D1 and D2.

If B1 wins on both, the result is much stronger than if it wins only on the easy-skewed production distribution.

---

## 6. RQ2 — What does optimization cost?

Do not describe the overhead as “negligible” unless the measurements support that statement.

### Measure end-to-end runtime

For every run record:

- candidate filtering time
- embedding generation time
- similarity-pair generation time
- conflict-graph construction time
- CP-SAT model construction time
- Pass 1 time
- Pass 2 time
- Pass 3 time
- total runtime

### Scaling

Run N = 100, 500, 1,000, 5,000, 10,000.

For every N report:

- median runtime
- p95 runtime
- number of conflict edges
- solver status
- memory if available

### Important plots

1. Total runtime vs N.
2. Runtime by pipeline stage vs N.
3. Conflict-edge count vs N.
4. B1/B0 runtime ratio vs N.

The last two plots are important because the O(n²) similarity stage may become the real bottleneck rather than CP-SAT.

---

## 7. RQ3 — When does optimization help?

This experiment should become one of the most interesting results in the paper.

For every tightness regime measure:

- feasibility rate
- B0 difficulty deviation
- B1 difficulty deviation
- B0−B1 quality gap
- topic coverage gap
- soft-compliance gap
- runtime overhead

Expected interpretation to test, not assume:

- If the feasible region is large, B0 may already find acceptable papers.
- If many feasible solutions exist with different quality, B1 should provide larger gains.
- If the feasible region collapses to one/few solutions, optimization should provide little additional benefit.
- In infeasible instances, both methods should fail closed.

Do not claim this pattern until measured.

---

## 8. RQ4 — Does the hybrid duplicate detector work?

This needs a separate evaluation dataset.

### Human-annotated pair set

Construct pairs from the question bank and label each pair:

- duplicate
- near duplicate
- legitimate numerical/structural variant
- unrelated

The most important category is legitimate numerical/structural variants because this is where the entity/token gate is supposed to help.

### Detectors

1. TF-IDF cosine
2. entity/token overlap only
3. pure SBERT cosine
4. SBERT + entity/token gate

### Metrics

- precision
- recall
- F1
- false-positive rate
- false-negative rate
- number of conflict edges

### Threshold sensitivity

SBERT thresholds:

- 0.75
- 0.80
- 0.85
- 0.90

Entity/token Jaccard thresholds:

- 0.30
- 0.50
- 0.70

### Critical implementation requirement

Do not rely on generic spaCy NER to recognize mathematical numbers unless the configured pipeline actually does so.

Define the mathematical entity/token extraction rule explicitly. It may include:

- numbers
- variables
- units
- named quantities
- domain-specific mathematical tokens

Then document exactly what is extracted.

---

## 9. RQ5 — Does optimization improve blueprint compliance?

Do not use one aggregate compliance score as the primary metric.

Report separately:

### Hard compliance

Expected to be 1.0 for every feasible method.

### Soft compliance

Primary metric.

Break it down into:

- difficulty-ratio compliance
- Bloom-level compliance
- competency/memory compliance
- other board-specific distributional requirements

This prevents an aggregate score from hiding a poor result in one dimension.

### Key comparison

B0 vs B1 on identical feasible instances.

Then compare B1 against B2/B3 to determine whether lexicographic ordering produces a better policy than scalarization or soft-window formulations.

---

## 10. Objective ablation

Run B1 variants:

### A1 — Difficulty only

Minimize D(x); no coverage/compliance optimization.

### A2 — Difficulty + coverage

The original two-level lexicographic formulation.

### A3 — Difficulty + coverage + soft compliance

Full B1.

### A4 — Coverage + compliance without difficulty

Tests whether difficulty is actually responsible for the primary improvement.

Expected use in paper:

- demonstrate that each objective contributes
- show the effect of objective ordering
- justify the three-pass design

---

## 11. B2 weight sensitivity

Do not choose a single α and β.

Use a grid such as:

- difficulty weight: 1, 2, 5, 10, 20
- coverage weight: 1, 2, 5, 10, 20
- compliance weight: 1, 2, 5, 10, 20

Normalize objectives before scalarization so weight comparisons are meaningful.

Report:

- D(x)
- C(x)
- S(x)

as a function of weights.

This supports the argument that lexicographic optimization avoids arbitrary cross-objective scaling.

---

## 12. Statistical protocol

For each experiment:

- use matched blueprint instances
- use multiple seeds for stochastic methods
- record all runs, including timeouts and infeasible cases
- report median and IQR for runtime
- report mean only where appropriate
- use paired Wilcoxon for B0 vs B1 quality metrics
- report effect size and 95% CI
- correct for multiple comparisons if many tests are performed

Do not delete failed runs from the dataset.

A timeout should be a timeout.
An infeasible instance should remain infeasible.

---

## 13. Minimum experiment matrix

A practical first complete run should contain:

| Experiment | Data | N | Blueprints | Methods | Seeds |
|---|---|---|---|---|---|
| RQ1 quality | D1 | 471 | 100–200 matched | B0, B0-R, BG, B1, B2, B3 | 5–10 |
| RQ1 balanced | D2 | 471 | 100–200 | B0, B0-R, BG, B1 | 5–10 |
| RQ2 scaling | D3 | 100–10k | 30–50/N | B0, B1 | 5 |
| RQ3 tightness | D1/D2 | 471 | 50/tier | B0, B1 | 5 |
| RQ4 detector | pair set | n/a | n/a | 4 detectors | n/a |
| RQ5 compliance | D1 | 471 | 100–200 | B0, B1, B2, B3 | 5–10 |
| Ablation | D1/D2 | 471 | 50–100 | A1–A4 | 5 |
| Weight sensitivity | D1 | 471 | 50–100 | B2 weight grid | 3–5 |

The exact number of instances can be reduced if computation becomes expensive, but the paired design should be preserved.

---

## 14. Data products to save

Every run should produce a row in a CSV/Parquet result file containing at least:

- experiment_id
- dataset_id
- pool_size
- blueprint_id
- tightness_tier
- method
- seed
- solver_status
- objective_D
- objective_coverage
- objective_soft_compliance
- hard_compliance
- soft_compliance
- selected_count
- selected_marks
- selected_time
- conflict_edges
- candidate_count
- preprocessing_time
- similarity_time
- model_time
- pass1_time
- pass2_time
- pass3_time
- total_time

Also save the selected question IDs for every successful run so individual generated papers can be inspected.

---

## 15. What must be completed before writing final Results

### Must have

- actual B0 implementation verified against production behavior
- actual B1 implementation
- exact B2 and B3 definitions
- mathematical entity/token extractor
- human-annotated duplicate-pair dataset
- blueprint generator
- tightness definition
- soft-compliance rule definitions
- balanced synthetic generator
- fixed random seeds
- complete runtime instrumentation
- statistical analysis script

### Must not remain

- placeholder percentages
- placeholder F1 values
- placeholder runtimes
- claims such as “negligible overhead” without measurements
- “production verified” unless the provenance is documented
- “CBSE compliant” unless the encoded rule set has actually been validated

---

## 16. Final figures recommended for the paper

1. **System architecture:** deployed pipeline and research extension.
2. **Optimization flow:** B0 vs B1, showing the three lexicographic passes.
3. **Duplicate-detection pipeline:** SBERT → mathematical entity/token gate → conflict graph.
4. **Quality comparison:** B0/B0-R/BG/B1/B2/B3.
5. **Runtime scaling:** N vs median/p95 runtime with stage decomposition.
6. **Tightness plot:** optimization gain vs feasible-region tightness.
7. **Detector evaluation:** precision/recall/F1 or threshold curves.
8. **Compliance decomposition:** difficulty/Bloom/competency soft-compliance components.

At 12-ish LNCS pages, only the strongest 5–6 figures should remain in the final manuscript; supplementary material can contain additional sensitivity plots.

---

## 17. Recommended experiment execution order

### Phase A — correctness

1. Reproduce B0.
2. Verify marks/time/count exactness.
3. Verify conflict constraints.
4. Verify B1 returns the mathematically correct lexicographic optimum on small toy instances by brute force.

### Phase B — detector

5. Build human pair labels.
6. Tune/evaluate detector thresholds.
7. Freeze the detector configuration before solver comparison.

### Phase C — benchmark

8. Build D1/D2/D3.
9. Generate blueprints.
10. Freeze seeds/configuration.

### Phase D — solver experiments

11. Run B0/B0-R/BG/B1/B2/B3.
12. Run ablations.
13. Run tightness experiments.
14. Run scaling experiments.

### Phase E — analysis

15. Statistical tests.
16. Confidence intervals/effect sizes.
17. Runtime decomposition.
18. Generate publication figures.

### Phase F — manuscript

19. Replace all placeholders.
20. Rewrite Abstract and Conclusion from measured results.
21. Update Discussion based on actual findings.
22. Freeze claims only after the statistical analysis is complete.
