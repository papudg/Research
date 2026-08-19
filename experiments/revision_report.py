"""Run independent-baseline and full-suite objective-ablation evidence."""
from __future__ import annotations

import json

import numpy as np
from scipy.stats import wilcoxon

from joint_policy_comparison import solve_joint_direct_compliance, solve_joint_lex
from multipolicy_benchmark import build_manifest, evaluate_blueprint
from revision_benchmark import evaluate_sequential, holm_adjust
from icaa.paths import results_path


CORE_POLICIES = ('b0', 'bls', 'b1', 'b2', 'bc', 'bj')
ABLATIONS = ('ablation_d', 'ablation_dc', 'ablation_dcp', 'ablation_cp')


def _evaluate_core(blueprint):
    return {
        'b0': evaluate_sequential(blueprint, 'b0'),
        'bls': evaluate_sequential(blueprint, 'local'),
        'b1': evaluate_sequential(blueprint, 'b1'),
        'b2': evaluate_blueprint(blueprint, 'b2'),
        'bc': solve_joint_direct_compliance(blueprint),
        'bj': solve_joint_lex(blueprint),
    }


def _summary(outcomes):
    result = {}
    for metric in ('difficulty', 'bloom_deviation', 'coverage', 'runtime_s'):
        values = np.asarray([outcome[metric] for outcome in outcomes], dtype=float)
        result[metric] = {
            'median': float(np.median(values)),
            'iqr': [float(value) for value in np.percentile(values, [25, 75])],
        }
    return result


def _paired(rows, baseline, reference='b1'):
    result = {}
    for metric in ('difficulty', 'bloom_deviation', 'coverage', 'runtime_s'):
        left = np.asarray([row['core'][baseline][metric] for row in rows], dtype=float)
        right = np.asarray([row['core'][reference][metric] for row in rows], dtype=float)
        # Positive differences favour B1 for every metric, including coverage.
        difference = right - left if metric == 'coverage' else left - right
        if len(difference) < 2 or not np.any(difference):
            p_value, effect = None, None
        else:
            test = wilcoxon(difference, method='approx')
            p_value = float(test.pvalue)
            effect = float(abs(test.zstatistic) / np.sqrt(len(difference)))
        rng = np.random.default_rng(20260818 + len(metric))
        bootstrap = [float(np.median(rng.choice(difference, len(difference), replace=True)))
                     for _ in range(3000)]
        result[metric] = {
            'median_difference_b1_favourable': float(np.median(difference)),
            'ci95': [float(value) for value in np.percentile(bootstrap, [2.5, 97.5])],
            'p_value': p_value,
            'effect_r': effect,
            'b1_wins': int((difference > 0).sum()),
            'ties': int((difference == 0).sum()),
            'baseline_wins': int((difference < 0).sum()),
        }
    return result


def _apply_holm(comparisons):
    targets = [(policy, metric, details['p_value'])
               for policy, metrics in comparisons.items()
               for metric, details in metrics.items()
               if details['p_value'] is not None]
    adjusted = holm_adjust([value for _, _, value in targets])
    for (policy, metric, _), value in zip(targets, adjusted):
        comparisons[policy][metric]['p_holm'] = value
    for metrics in comparisons.values():
        for details in metrics.values():
            if 'p_holm' not in details:
                details['p_holm'] = None


def run_revision_suite(manifest=None):
    manifest = build_manifest() if manifest is None else manifest
    rows = []
    for blueprint in manifest:
        core = _evaluate_core(blueprint)
        ablations = {policy: evaluate_sequential(blueprint, policy) for policy in ABLATIONS}
        rows.append({'blueprint': blueprint, 'core': core, 'ablations': ablations})
    core_common = [row for row in rows if all(row['core'][policy]['outcome'] == 'feasible'
                                              for policy in CORE_POLICIES)]
    ablation_common = [row for row in rows if all(row['ablations'][policy]['outcome'] == 'feasible'
                                                  for policy in ABLATIONS)]
    core_summary = {policy: _summary([row['core'][policy] for row in core_common])
                    for policy in CORE_POLICIES}
    comparisons = {policy: _paired(core_common, policy) for policy in CORE_POLICIES if policy != 'b1'}
    _apply_holm(comparisons)
    ablation_summary = {policy: _summary([row['ablations'][policy] for row in ablation_common])
                        for policy in ABLATIONS}
    return {
        'scheduled_count': len(rows),
        'core_common_count': len(core_common),
        'ablation_common_count': len(ablation_common),
        'core_policies': list(CORE_POLICIES),
        'core_summary': core_summary,
        'comparisons_vs_b1': comparisons,
        'ablation_summary': ablation_summary,
        'rows': rows,
    }


def _format(report):
    lines = [f"revision suite: {report['core_common_count']}/{report['scheduled_count']} core-common; "
             f"{report['ablation_common_count']}/{report['scheduled_count']} ablation-common",
             'policy | median D [IQR] | median Bloom [IQR] | median coverage [IQR] | median solver s [IQR]']
    for policy, values in report['core_summary'].items():
        lines.append(f"{policy.upper()} | {values['difficulty']['median']} {values['difficulty']['iqr']} | "
                     f"{values['bloom_deviation']['median']} {values['bloom_deviation']['iqr']} | "
                     f"{values['coverage']['median']} {values['coverage']['iqr']} | "
                     f"{values['runtime_s']['median']:.3f} {values['runtime_s']['iqr']}")
    lines.append('paired comparisons versus B1 (positive difference favours B1; Holm across all reported tests):')
    for policy, metrics in report['comparisons_vs_b1'].items():
        details = metrics['difficulty']
        lines.append(f"{policy.upper()} D: diff={details['median_difference_b1_favourable']}, "
                     f"CI={details['ci95']}, p={details['p_value']}, p_holm={details['p_holm']}, "
                     f"r={details['effect_r']}, wins/ties/losses={details['b1_wins']}/{details['ties']}/{details['baseline_wins']}")
    lines.append('full-suite objective ablations:')
    for policy, values in report['ablation_summary'].items():
        lines.append(f"{policy}: D={values['difficulty']['median']} {values['difficulty']['iqr']}; "
                     f"Bloom={values['bloom_deviation']['median']} {values['bloom_deviation']['iqr']}; "
                     f"coverage={values['coverage']['median']} {values['coverage']['iqr']}")
    return '\n'.join(lines)


if __name__ == '__main__':
    result = run_revision_suite()
    with open(results_path('results_revision_suite.json'), 'w', encoding='utf-8') as output:
        json.dump(result, output, indent=2)
    print(_format(result))
