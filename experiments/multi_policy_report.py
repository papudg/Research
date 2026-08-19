"""Aggregate the shared multi-policy suite and persist auditable RQ1 artifacts."""
import json
from collections import Counter

import numpy as np
from scipy.stats import wilcoxon

from multipolicy_benchmark import POLICIES, run_suite
from icaa.paths import results_path


def _median(values):
    return float(np.median(values)) if values else None


def _pairwise(rows, baseline, reference='b1'):
    left = np.array([row['outcomes'][baseline]['difficulty'] for row in rows], dtype=float)
    right = np.array([row['outcomes'][reference]['difficulty'] for row in rows], dtype=float)
    bloom_left = np.array([row['outcomes'][baseline]['bloom_deviation'] for row in rows], dtype=float)
    bloom_right = np.array([row['outcomes'][reference]['bloom_deviation'] for row in rows], dtype=float)
    rng = np.random.default_rng(42)

    def statistic(a, b):
        difference = a - b
        if len(a) < 2 or not np.any(difference):
            p_value, effect = None, None
        else:
            test = wilcoxon(a, b, method='approx')
            p_value = float(test.pvalue)
            effect = float(abs(test.zstatistic) / np.sqrt(len(a)))
        bootstrap = [float(np.median(rng.choice(difference, len(difference), replace=True))) for _ in range(3000)]
        return {'median_difference': float(np.median(difference)), 'p_value': p_value, 'effect_r': effect,
                'ci95': [float(value) for value in np.percentile(bootstrap, [2.5, 97.5])],
                'wins': int((difference > 0).sum()), 'ties': int((difference == 0).sum())}

    return {'difficulty': statistic(left, right), 'bloom_deviation': statistic(bloom_left, bloom_right)}


def aggregate(suite):
    common_ids = set(suite['common_feasible_ids'])
    common_rows = [row for row in suite['rows'] if row['blueprint']['id'] in common_ids]
    exclusions = Counter()
    failure_events = []
    outcome_counts = {policy: Counter() for policy in POLICIES}
    for row in suite['rows']:
        blueprint_id = row['blueprint']['id']
        for policy in POLICIES:
            outcome_counts[policy][row['outcomes'][policy]['outcome']] += 1
        failures = [{'policy': policy, 'outcome': row['outcomes'][policy]['outcome']}
                    for policy in POLICIES if row['outcomes'][policy]['outcome'] != 'feasible']
        if failures:
            primary = failures[0]
            exclusions[f"{primary['policy']}:{primary['outcome']}"] += 1
            failure_events.append({'blueprint_id': blueprint_id, 'primary_reason': primary, 'all_failures': failures})
    medians = {}
    for policy in POLICIES:
        outcomes = [row['outcomes'][policy] for row in common_rows]
        medians[policy] = {
            'difficulty': _median([outcome['difficulty'] for outcome in outcomes]),
            'bloom_deviation': _median([outcome['bloom_deviation'] for outcome in outcomes]),
            'coverage': _median([outcome['coverage'] for outcome in outcomes]),
            'runtime_s': _median([outcome['runtime_s'] for outcome in outcomes]),
        }
    comparisons = {policy: _pairwise(common_rows, policy) for policy in POLICIES if policy != 'b1'}
    return {'scheduled_count': len(suite['manifest']), 'common_feasible_count': len(common_rows),
            'outcome_counts': {policy: dict(sorted(counts.items())) for policy, counts in outcome_counts.items()},
            'exclusion_counts': dict(sorted(exclusions.items())), 'failure_events': failure_events,
            'medians': medians, 'comparisons_vs_b1': comparisons, 'common_feasible_ids': sorted(common_ids),
            'rows': suite['rows']}


def _format(report):
    lines = [f"multi-policy: {report['common_feasible_count']}/{report['scheduled_count']} common-feasible blueprints",
             'outcomes by policy:']
    lines.extend(f"  {policy.upper()}: " + ', '.join(f'{outcome}={count}' for outcome, count in counts.items())
                 for policy, counts in report['outcome_counts'].items())
    lines.append('exclusion breakdown (one primary policy/outcome per excluded blueprint):')
    lines.extend(f'  {reason}: {count}' for reason, count in report['exclusion_counts'].items())
    lines.append('\nmethod  median_D  median_Bloom  median_coverage  median_solver_s')
    for policy, values in report['medians'].items():
        lines.append(f"{policy.upper():<6} {values['difficulty']:8.1f} {values['bloom_deviation']:13.1f} {values['coverage']:16.1f} {values['runtime_s']:16.3f}")
    lines.append('\npaired B1 comparisons (positive difference favours B1):')
    for policy, metrics in report['comparisons_vs_b1'].items():
        difficulty, bloom = metrics['difficulty'], metrics['bloom_deviation']
        lines.append(f"{policy.upper()} vs B1 | D median diff={difficulty['median_difference']:.1f}, p={difficulty['p_value']}, r={difficulty['effect_r']}, CI={difficulty['ci95']}; Bloom median diff={bloom['median_difference']:.1f}, p={bloom['p_value']}, r={bloom['effect_r']}, CI={bloom['ci95']}")
    return '\n'.join(lines)


if __name__ == '__main__':
    report = aggregate(run_suite())
    with open(results_path('results_multi_policy.json'), 'w', encoding='utf-8') as output:
        json.dump(report, output, indent=2)
    print(_format(report))
