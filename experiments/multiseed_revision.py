"""Robustness study over independently generated blueprint manifests."""
from __future__ import annotations

import json

import numpy as np

from multipolicy_benchmark import build_manifest
from revision_report import CORE_POLICIES, _apply_holm, _evaluate_core, _paired, _summary
from icaa.paths import results_path


SEEDS = (42, 43, 44, 45, 46)


def _cluster_bootstrap(runs, policy, metric, samples=5000):
    """Bootstrap manifest-level median differences, treating seeds as clusters."""
    values = np.asarray([
        run['seed_comparisons'][policy][metric]['median_difference_b1_favourable']
        for run in runs
    ], dtype=float)
    rng = np.random.default_rng(20260818 + len(policy) + len(metric))
    draws = [float(np.median(rng.choice(values, len(values), replace=True))) for _ in range(samples)]
    return {
        'seed_level_median_differences_b1_favourable': [float(value) for value in values],
        'median_of_seed_differences': float(np.median(values)),
        'cluster_bootstrap_ci95': [float(value) for value in np.percentile(draws, [2.5, 97.5])],
    }


def run_multiseed(seeds=SEEDS, count=80):
    runs, pooled = [], []
    for seed in seeds:
        manifest = build_manifest(seed=seed, count=count)
        rows = []
        for blueprint in manifest:
            rows.append({'blueprint': blueprint, 'core': _evaluate_core(blueprint)})
        common = [row for row in rows if all(row['core'][policy]['outcome'] == 'feasible'
                                             for policy in CORE_POLICIES)]
        seed_comparisons = {policy: _paired(common, policy)
                            for policy in CORE_POLICIES if policy != 'b1'}
        _apply_holm(seed_comparisons)
        runs.append({
            'seed': seed,
            'scheduled_count': count,
            'common_count': len(common),
            'policy_summary': {policy: _summary([row['core'][policy] for row in common])
                               for policy in CORE_POLICIES},
            'seed_comparisons': seed_comparisons,
            'rows': rows,
        })
        pooled.extend(common)
    comparisons = {policy: _paired(pooled, policy) for policy in CORE_POLICIES if policy != 'b1'}
    _apply_holm(comparisons)
    manifest_distributions = {}
    for policy in CORE_POLICIES:
        manifest_distributions[policy] = {}
        for metric in ('difficulty', 'bloom_deviation', 'coverage', 'runtime_s'):
            medians = np.asarray([run['policy_summary'][policy][metric]['median'] for run in runs], dtype=float)
            manifest_distributions[policy][metric] = {
                'seed_medians': [float(value) for value in medians],
                'median_of_seed_medians': float(np.median(medians)),
                'iqr_of_seed_medians': [float(value) for value in np.percentile(medians, [25, 75])],
            }
    cluster_bootstrap = {
        policy: {metric: _cluster_bootstrap(runs, policy, metric)
                 for metric in ('difficulty', 'bloom_deviation', 'coverage', 'runtime_s')}
        for policy in CORE_POLICIES if policy != 'b1'
    }
    return {'seeds': list(seeds), 'scheduled_per_seed': count, 'runs': runs,
            'pooled_common_count': len(pooled), 'manifest_distributions': manifest_distributions,
            'comparisons_vs_b1': comparisons, 'cluster_bootstrap_vs_b1': cluster_bootstrap}


def _format(report):
    lines = [f"multi-seed revision: seeds={report['seeds']}; {report['scheduled_per_seed']} blueprints/seed",
             'seed | common feasible']
    lines.extend(f"{run['seed']} | {run['common_count']}" for run in report['runs'])
    lines.append('policy | D seed medians [IQR] | Bloom seed medians [IQR] | coverage seed medians [IQR]')
    for policy, metrics in report['manifest_distributions'].items():
        lines.append(f"{policy.upper()} | {metrics['difficulty']['seed_medians']} {metrics['difficulty']['iqr_of_seed_medians']} | "
                     f"{metrics['bloom_deviation']['seed_medians']} {metrics['bloom_deviation']['iqr_of_seed_medians']} | "
                     f"{metrics['coverage']['seed_medians']} {metrics['coverage']['iqr_of_seed_medians']}")
    lines.append('seed-level difficulty effects versus B1 (median difference and cluster bootstrap CI):')
    for policy, metrics in report['cluster_bootstrap_vs_b1'].items():
        details = metrics['difficulty']
        lines.append(f"{policy.upper()}: {details['seed_level_median_differences_b1_favourable']}; "
                     f"median={details['median_of_seed_differences']}, CI={details['cluster_bootstrap_ci95']}")
    lines.append('pooled paired comparisons versus B1 (positive difference favours B1; Holm adjusted):')
    for policy, metrics in report['comparisons_vs_b1'].items():
        details = metrics['difficulty']
        lines.append(f"{policy.upper()} D: diff={details['median_difference_b1_favourable']}, CI={details['ci95']}, "
                     f"p={details['p_value']}, p_holm={details['p_holm']}, r={details['effect_r']}, "
                     f"wins/ties/losses={details['b1_wins']}/{details['ties']}/{details['baseline_wins']}")
    return '\n'.join(lines)


if __name__ == '__main__':
    result = run_multiseed()
    with open(results_path('results_multiseed_revision.json'), 'w', encoding='utf-8') as output:
        json.dump(result, output, indent=2)
    print(_format(result))
