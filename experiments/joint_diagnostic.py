"""Joint whole-paper feasibility diagnostic for sequential RQ1 continuation failures."""
import json
import time
from collections import Counter, defaultdict

from generate import chapter, chapters_of, cp_model, load_bank
from icaa.paths import results_path


BANK = load_bank()
CHAP = chapters_of(BANK)
VALID = (cp_model.OPTIMAL, cp_model.FEASIBLE)


def _outcome(status):
    name = str(status).upper()
    if status in VALID:
        return 'feasible'
    if 'INFEASIBLE' in name:
        return 'infeasible'
    if 'UNKNOWN' in name:
        return 'unknown'
    return 'error'


def evaluate_joint_feasibility(blueprint, bank=None, chapset=None, conflict=None):
    """Solve all blueprint sections jointly under their sequential hard constraints."""
    bank = BANK if bank is None else bank
    chapset = CHAP if chapset is None else chapset
    eligible = set(blueprint['eligible_chapters'])
    conflict = conflict or []
    started = time.perf_counter()
    try:
        model = cp_model.CpModel()
        variables = {}
        by_id = defaultdict(list)
        section_pools = {}
        for section in blueprint['sections']:
            name = section['name']
            pool = [item for item in bank
                    if chapter(item, chapset) in eligible and int(item['marks']) == section['tier']]
            section_pools[name] = pool
            for item in pool:
                variable = model.NewBoolVar(f"{name}_{item['id']}")
                variables[(name, item['id'])] = variable
                by_id[item['id']].append(variable)
            section_variables = [variables[(name, item['id'])] for item in pool]
            model.Add(sum(section_variables) == section['question_count'])
            model.Add(sum(int(item['marks']) * variables[(name, item['id'])] for item in pool) == section['marks'])
            model.Add(sum(int(item['time']) * variables[(name, item['id'])] for item in pool) == section['time'])

        for item_variables in by_id.values():
            model.Add(sum(item_variables) <= 1)
        for left, right in conflict:
            if left in by_id and right in by_id:
                model.Add(sum(by_id[left]) + sum(by_id[right]) <= 1)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 30
        solver.parameters.random_seed = 1
        solver.parameters.num_search_workers = 1
        status = solver.Solve(model)
        outcome = _outcome(status)
        result = {'outcome': outcome, 'status': str(status), 'runtime_s': time.perf_counter() - started,
                  'sections': None}
        if outcome == 'feasible':
            result['sections'] = {
                name: [item['id'] for item in pool if solver.Value(variables[(name, item['id'])])]
                for name, pool in section_pools.items()
            }
        return result
    except Exception as error:
        return {'outcome': 'error', 'status': f'{type(error).__name__}: {error}',
                'runtime_s': time.perf_counter() - started, 'sections': None}


def run_joint_diagnostic(report, bank=None, chapset=None, conflict=None):
    """Diagnose exactly the blueprint IDs excluded from the sequential common set."""
    diagnosed_ids = sorted({event['blueprint_id'] for event in report['failure_events']})
    rows = {row['blueprint']['id']: row['blueprint'] for row in report['rows']}
    outcomes = []
    for blueprint_id in diagnosed_ids:
        result = evaluate_joint_feasibility(rows[blueprint_id], bank=bank, chapset=chapset, conflict=conflict)
        outcomes.append({'blueprint_id': blueprint_id, **result})
    return {'diagnosed_ids': diagnosed_ids, 'diagnosed_count': len(diagnosed_ids),
            'outcome_counts': dict(sorted(Counter(item['outcome'] for item in outcomes).items())),
            'outcomes': outcomes}


def _format(report):
    lines = [f"joint whole-paper diagnostic: {report['diagnosed_count']} sequential continuation failures",
             'outcomes: ' + ', '.join(f'{outcome}={count}' for outcome, count in report['outcome_counts'].items()),
             'blueprint | outcome | CP-SAT status | solver runtime (s)']
    lines.extend(f"{item['blueprint_id']} | {item['outcome']} | {item['status']} | {item['runtime_s']:.3f}"
                 for item in report['outcomes'])
    return '\n'.join(lines)


if __name__ == '__main__':
    with open(results_path('results_multi_policy.json'), encoding='utf-8') as source:
        multi_policy = json.load(source)
    result = run_joint_diagnostic(multi_policy)
    with open(results_path('results_joint_whole_paper.json'), 'w', encoding='utf-8') as output:
        json.dump(result, output, indent=2)
    print(_format(result))
