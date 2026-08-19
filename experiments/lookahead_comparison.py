"""Compare bounded lookahead-guided sequential B1 with ordinary sequential B1."""
from __future__ import annotations

import json
import statistics
import time

from multipolicy_benchmark import build_manifest
from revision_benchmark import evaluate_sequential
from icaa.paths import results_path


def _median(values):
    return statistics.median(values) if values else None


def _iqr(values):
    if not values:
        return [None, None]
    ordered = sorted(values)
    return [ordered[len(ordered) // 4], ordered[(3 * len(ordered)) // 4]]


def run(manifest=None):
    manifest = manifest or build_manifest(seed=42, count=80)
    rows = []
    for blueprint in manifest:
        started = time.perf_counter()
        sequential = evaluate_sequential(blueprint, 'b1')
        lookahead = evaluate_sequential(blueprint, 'lookahead')
        rows.append({'blueprint': blueprint['id'], 'sequential': sequential, 'lookahead': lookahead,
                     'wall_s': time.perf_counter() - started})
    comparable = [row for row in rows
                  if row['sequential']['outcome'] == 'feasible'
                  and row['lookahead']['outcome'] == 'feasible']
    metrics = ('difficulty', 'bloom_deviation', 'coverage', 'runtime_s')
    summary = {'scheduled_count': len(rows), 'comparable_count': len(comparable), 'rows': rows,
               'parameters': {'k': 3, 'epsilon': 0, 'max_time_per_subsolve_s': 5,
                              'future_score': '100 exact-relaxed-feasibility - 100 failure + normalized support - normalized conflict load'}}
    for metric in metrics:
        base = [row['sequential'][metric] for row in comparable]
        guided = [row['lookahead'][metric] for row in comparable]
        differences = [b - g for b, g in zip(base, guided)]
        summary[metric] = {
            'sequential_median': _median(base), 'sequential_iqr': _iqr(base),
            'lookahead_median': _median(guided), 'lookahead_iqr': _iqr(guided),
            'lookahead_favourable_median_difference': _median(differences),
            'lookahead_wins_ties_sequential_wins': [sum(d > 0 for d in differences),
                                                     sum(d == 0 for d in differences),
                                                     sum(d < 0 for d in differences)],
        }
    return summary


def render(summary):
    lines = [f"lookahead comparison: {summary['comparable_count']}/{summary['scheduled_count']} comparable blueprints",
             'metric | sequential median [IQR] | lookahead median [IQR] | guided-favourable difference | guided wins/ties/sequential wins']
    for metric in ('difficulty', 'bloom_deviation', 'coverage', 'runtime_s'):
        values = summary[metric]
        lines.append(f"{metric} | {values['sequential_median']} {values['sequential_iqr']} | "
                     f"{values['lookahead_median']} {values['lookahead_iqr']} | "
                     f"{values['lookahead_favourable_median_difference']} | "
                     f"{'/'.join(map(str, values['lookahead_wins_ties_sequential_wins']))}")
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    result = run()
    with open(results_path('results_lookahead_comparison.json'), 'w', encoding='utf-8') as output:
        json.dump(result, output, indent=2)
    with open(results_path('results_lookahead_comparison.txt'), 'w', encoding='utf-8') as output:
        output.write(render(result))
    print(render(result), end='')
