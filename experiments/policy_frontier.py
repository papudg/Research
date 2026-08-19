"""Observed policy/weight frontier for ten fixed common-feasible blueprints."""
import json
from collections import Counter

from icaa.paths import results_path


def dominates(left, right):
    no_worse = (left['difficulty'] <= right['difficulty'] and
                left['bloom_deviation'] <= right['bloom_deviation'] and
                left['coverage'] >= right['coverage'] and
                left['runtime_s'] <= right['runtime_s'])
    strictly_better = (left['difficulty'] < right['difficulty'] or
                       left['bloom_deviation'] < right['bloom_deviation'] or
                       left['coverage'] > right['coverage'] or
                       left['runtime_s'] < right['runtime_s'])
    return no_worse and strictly_better


def frontier(points):
    return [point for point in points if not any(other is not point and dominates(other, point) for other in points)]


def run_frontier(multi_policy, sensitivity, limit=10):
    selected_ids = multi_policy['common_feasible_ids'][:limit]
    multi_rows = {row['blueprint']['id']: row for row in multi_policy['rows']}
    weight_rows = sensitivity['b2_weight_rows']
    per_blueprint = []
    policy_counts = Counter()
    for blueprint_id in selected_ids:
        outcomes = multi_rows[blueprint_id]['outcomes']
        points = []
        for policy in ('b0', 'bg', 'b1', 'b3'):
            points.append({'label': policy.upper(), **outcomes[policy]})
        for weight_row in weight_rows:
            outcome = next(item for item in weight_row['outcomes'] if item['blueprint_id'] == blueprint_id)
            weights = weight_row['weights']
            points.append({'label': f"B2({weights['alpha']},{weights['beta']},{weights['gamma']})", **outcome})
        nondominated = frontier(points)
        policy_counts.update(point['label'] for point in nondominated)
        per_blueprint.append({'blueprint_id': blueprint_id, 'candidate_count': len(points), 'frontier': nondominated})
    return {'scope': 'observed policy/weight frontier; not exhaustive Pareto optimization',
            'blueprint_ids': selected_ids, 'per_blueprint': per_blueprint,
            'frontier_label_counts': dict(sorted(policy_counts.items()))}


def _format(result):
    lines = [f"observed policy frontier: {len(result['blueprint_ids'])} fixed common-feasible blueprints",
             result['scope'], 'blueprint | candidates | non-dominated labels']
    for row in result['per_blueprint']:
        lines.append(f"{row['blueprint_id']} | {row['candidate_count']} | {', '.join(point['label'] for point in row['frontier'])}")
    lines.append('frontier membership counts:')
    lines.extend(f'  {label}: {count}' for label, count in result['frontier_label_counts'].items())
    return '\n'.join(lines)


if __name__ == '__main__':
    with open(results_path('results_multi_policy.json'), encoding='utf-8') as source:
        multi_policy = json.load(source)
    with open(results_path('results_weight_sensitivity.json'), encoding='utf-8') as source:
        sensitivity = json.load(source)
    result = run_frontier(multi_policy, sensitivity)
    with open(results_path('results_policy_frontier.json'), 'w', encoding='utf-8') as output:
        json.dump(result, output, indent=2)
    print(_format(result))
