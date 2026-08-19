"""Audit CP-SAT pass statuses for B1 on the RQ1 common-feasible suite."""
import json
from collections import Counter

from baselines import BANK, CHAP, COVER
from generate import solve_b1
from icaa.paths import results_path


def summarize_statuses(statuses):
    return dict(sorted(Counter(statuses).items()))


def run_status_audit(multi_policy):
    common_ids = set(multi_policy['common_feasible_ids'])
    rows = sorted((row for row in multi_policy['rows'] if row['blueprint']['id'] in common_ids),
                  key=lambda row: row['blueprint']['id'])
    statuses = []
    section_count = 0
    for row in rows:
        blueprint = row['blueprint']
        used = set()
        for raw_section in blueprint['sections']:
            section = dict(raw_section)
            delta = {int(band): value for band, value in raw_section['difficulty_target'].items()}
            result, outcome = solve_b1(BANK, section['question_count'], section['marks'], section['time'],
                                       set(blueprint['eligible_chapters']), CHAP, delta, COVER,
                                       section['bloom_target'], marks_tier=section['tier'], exclude=used)
            if outcome != 'ok':
                raise RuntimeError(f"{blueprint['id']} section {section['name']} returned {outcome}")
            statuses.extend(result['pass_statuses'])
            used.update(result['sel'])
            section_count += 1
    return {'blueprint_count': len(rows), 'section_count': section_count,
            'pass_count': len(statuses), 'status_counts': summarize_statuses(statuses)}


def _format(audit):
    counts = ', '.join(f'{status}={count}' for status, count in audit['status_counts'].items())
    return (f"B1 status audit: {audit['blueprint_count']} common-feasible blueprints, "
            f"{audit['section_count']} sections, {audit['pass_count']} passes\n{counts}")


if __name__ == '__main__':
    with open(results_path('results_multi_policy.json'), encoding='utf-8') as source:
        multi_policy = json.load(source)
    audit = run_status_audit(multi_policy)
    with open(results_path('results_b1_status_audit.json'), 'w', encoding='utf-8') as output:
        json.dump(audit, output, indent=2)
    print(_format(audit))
