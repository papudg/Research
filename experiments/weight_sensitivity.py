"""Three-axis B2 weight sensitivity on the shared common-feasible blueprint set."""
import itertools
import json
from statistics import median

from multipolicy_benchmark import evaluate_blueprint
from icaa.paths import results_path


def weight_grid():
    return list(itertools.product((1, 3, 10), repeat=3))


def _summary(outcomes):
    return {
        'difficulty': median(outcome['difficulty'] for outcome in outcomes),
        'bloom_deviation': median(outcome['bloom_deviation'] for outcome in outcomes),
        'coverage': median(outcome['coverage'] for outcome in outcomes),
        'runtime_s': median(outcome['runtime_s'] for outcome in outcomes),
    }


def run_sensitivity(report):
    common = [row for row in report['rows'] if row['blueprint']['id'] in set(report['common_feasible_ids'])]
    rows = []
    for weights in weight_grid():
        outcomes = []
        for row in common:
            outcome = evaluate_blueprint(row['blueprint'], 'b2', weights)
            if outcome['outcome'] != 'feasible':
                raise RuntimeError(f"B2 became {outcome['outcome']} for {row['blueprint']['id']} at {weights}")
            outcomes.append({'blueprint_id': row['blueprint']['id'], **outcome})
        rows.append({'weights': {'alpha': weights[0], 'beta': weights[1], 'gamma': weights[2]},
                     'summary': _summary(outcomes), 'outcomes': outcomes})
    b1_outcomes = [{'blueprint_id': row['blueprint']['id'], **row['outcomes']['b1']} for row in common]
    return {'common_feasible_count': len(common), 'b2_weight_rows': rows, 'b1_reference': _summary(b1_outcomes)}


def _format(result):
    lines = [f"B2 three-weight sensitivity: {result['common_feasible_count']} common-feasible blueprints",
             'alpha beta gamma | median_D median_Bloom median_coverage median_solver_s']
    for row in result['b2_weight_rows']:
        weights, summary = row['weights'], row['summary']
        lines.append(f"{weights['alpha']:5} {weights['beta']:4} {weights['gamma']:5} | {summary['difficulty']:8.1f} {summary['bloom_deviation']:12.1f} {summary['coverage']:15.1f} {summary['runtime_s']:15.3f}")
    reference = result['b1_reference']
    lines.append(f"B1 no-weight reference | {reference['difficulty']:8.1f} {reference['bloom_deviation']:12.1f} {reference['coverage']:15.1f} {reference['runtime_s']:15.3f}")
    return '\n'.join(lines)


if __name__ == '__main__':
    with open(results_path('results_multi_policy.json'), encoding='utf-8') as source:
        result = run_sensitivity(json.load(source))
    with open(results_path('results_weight_sensitivity.json'), 'w', encoding='utf-8') as output:
        json.dump(result, output, indent=2)
    print(_format(result))
