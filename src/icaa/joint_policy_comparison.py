"""Joint whole-paper policy comparison and sequential section-order study."""
from __future__ import annotations

import json
import time
from collections import Counter

import numpy as np

from icaa.baselines import BANK, CHAP, COVER, bloom_target
from icaa.generate import chapter, cp_model, diff
from icaa.multipolicy_benchmark import build_manifest
from icaa.paths import results_path
from icaa.revision_benchmark import _group, _pool, evaluate_sequential

ORDERINGS = {
    'production_A_B_C_D_E': ('A', 'B', 'C', 'D', 'E'),
    'reverse_E_D_C_B_A': ('E', 'D', 'C', 'B', 'A'),
    'high_count_A_C_B_D_E': ('A', 'C', 'B', 'D', 'E'),
    'low_count_E_D_B_C_A': ('E', 'D', 'B', 'C', 'A'),
}


def _section_difficulty(ids, by_id, target):
    counts = Counter(diff(by_id[identifier]) for identifier in ids)
    return sum(abs(counts.get(band, 0) - value) for band, value in target.items())


def _paper_metrics(sections, by_id, chapset):
    ids = [identifier for section in sections.values() for identifier in section]
    bloom_counts = Counter(bloom for bloom in (_group(by_id[identifier]) for identifier in ids) if bloom)
    target = bloom_target(len(ids))
    bloom_deviation = sum(abs(bloom_counts.get(group, 0) - target[group]) for group in target)
    coverage = len({chapter(by_id[identifier], chapset) for identifier in ids})
    return bloom_deviation, coverage


def _new_solver():
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    solver.parameters.random_seed = 1
    solver.parameters.num_search_workers = 1
    return solver


def _solve(model):
    solver = _new_solver()
    status = solver.Solve(model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return solver, 'feasible', str(status)
    if status == cp_model.INFEASIBLE:
        return None, 'infeasible', str(status)
    return None, 'unknown', str(status)


def solve_joint_lex(blueprint, bank=None, chapset=None, cover_topics=None):
    bank = BANK if bank is None else bank
    chapset = CHAP if chapset is None else chapset
    cover_topics = COVER if cover_topics is None else list(cover_topics)
    eligible = set(blueprint['eligible_chapters'])
    model = cp_model.CpModel()
    section_data, by_item = {}, {}
    by_id = {question['id']: question for question in bank}
    total_difficulty, total_coverage, total_bloom = [], [], []
    started = time.perf_counter()
    for raw in blueprint['sections']:
        section = dict(raw)
        section['difficulty_target'] = {int(band): target for band, target in raw['difficulty_target'].items()}
        name = section['name']
        pool = _pool(bank, eligible, chapset, section['tier'])
        variables = {question['id']: model.NewBoolVar(f'x_{name}_{question["id"]}') for question in pool}
        model.Add(sum(int(question['marks']) * variables[question['id']] for question in pool) == section['marks'])
        model.Add(sum(int(question['time']) * variables[question['id']] for question in pool) == section['time'])
        model.Add(sum(variables.values()) == section['question_count'])
        for identifier, variable in variables.items():
            by_item.setdefault(identifier, []).append(variable)
        deviations = {band: model.NewIntVar(0, section['question_count'], f'd_{name}_{band}')
                      for band in section['difficulty_target']}
        for band, target in section['difficulty_target'].items():
            count = sum(variables[question['id']] for question in pool if diff(question) == band)
            model.Add(deviations[band] >= count - target)
            model.Add(deviations[band] >= target - count)
        coverage = {topic: model.NewBoolVar(f'c_{name}_{index}') for index, topic in enumerate(cover_topics)}
        for topic in cover_topics:
            model.Add(coverage[topic] <= sum(variables[question['id']] for question in pool
                                             if chapter(question, chapset) == topic))
        bloom_deviation = {group: model.NewIntVar(0, section['question_count'], f'p_{name}_{group}')
                           for group in section['bloom_target']}
        for group, target in section['bloom_target'].items():
            count = sum(variables[question['id']] for question in pool if _group(question) == group)
            model.Add(bloom_deviation[group] >= count - target)
            model.Add(bloom_deviation[group] >= target - count)
        section_data[name] = (section, pool, variables, deviations)
        total_difficulty.extend(deviations.values())
        total_coverage.extend(coverage.values())
        total_bloom.extend(bloom_deviation.values())
    for variables in by_item.values():
        if len(variables) > 1:
            model.Add(sum(variables) <= 1)
    pass_statuses = []
    difficulty_expr, coverage_expr, bloom_expr = sum(total_difficulty), sum(total_coverage), sum(total_bloom)
    solver = None
    for expression, direction, lock_name in ((difficulty_expr, 'min', 'D'),
                                              (coverage_expr, 'max', 'C'),
                                              (bloom_expr, 'min', 'P')):
        if direction == 'min':
            model.Minimize(expression)
        else:
            model.Maximize(expression)
        solver, outcome, raw_status = _solve(model)
        pass_statuses.append({'pass': lock_name, 'status': raw_status})
        if solver is None:
            return {'outcome': outcome, 'runtime_s': time.perf_counter() - started,
                    'pass_statuses': pass_statuses}
        value = round(solver.ObjectiveValue())
        if direction == 'min':
            model.Add(expression <= value)
        else:
            model.Add(expression >= value)
    selected, section_rows, difficulty = {}, [], 0
    for name, (section, pool, variables, _) in section_data.items():
        ids = [question['id'] for question in pool if solver.Value(variables[question['id']])]
        selected[name] = ids
        section_difficulty = _section_difficulty(ids, by_id, section['difficulty_target'])
        difficulty += section_difficulty
        section_rows.append({'section': name, 'difficulty': section_difficulty,
                             'question_count': section['question_count']})
    bloom_deviation, coverage = _paper_metrics(selected, by_id, chapset)
    return {'outcome': 'feasible', 'difficulty': difficulty, 'bloom_deviation': bloom_deviation,
            'coverage': coverage, 'runtime_s': time.perf_counter() - started, 'sections': selected,
            'section_rows': section_rows, 'pass_statuses': pass_statuses}


def solve_joint_direct_compliance(blueprint, bank=None, chapset=None):
    bank = BANK if bank is None else bank
    chapset = CHAP if chapset is None else chapset
    eligible = set(blueprint['eligible_chapters'])
    model = cp_model.CpModel()
    section_data, by_item, all_variables = {}, {}, []
    total_difficulty = []
    total_questions = 0
    started = time.perf_counter()
    for raw in blueprint['sections']:
        section = dict(raw)
        section['difficulty_target'] = {int(band): target for band, target in raw['difficulty_target'].items()}
        name = section['name']
        pool = _pool(bank, eligible, chapset, section['tier'])
        variables = {question['id']: model.NewBoolVar(f'x_{name}_{question["id"]}') for question in pool}
        model.Add(sum(int(question['marks']) * variables[question['id']] for question in pool) == section['marks'])
        model.Add(sum(int(question['time']) * variables[question['id']] for question in pool) == section['time'])
        model.Add(sum(variables.values()) == section['question_count'])
        for identifier, variable in variables.items():
            by_item.setdefault(identifier, []).append(variable)
        deviations = {band: model.NewIntVar(0, section['question_count'], f'd_{name}_{band}')
                      for band in section['difficulty_target']}
        for band, target in section['difficulty_target'].items():
            count = sum(variables[question['id']] for question in pool if diff(question) == band)
            model.Add(deviations[band] >= count - target)
            model.Add(deviations[band] >= target - count)
        section_data[name] = (section, pool, variables)
        total_difficulty.extend(deviations.values())
        total_questions += section['question_count']
        all_variables.extend((question, variables[question['id']]) for question in pool)
    for variables in by_item.values():
        if len(variables) > 1:
            model.Add(sum(variables) <= 1)
    global_target = bloom_target(total_questions)
    global_bloom = {group: model.NewIntVar(0, total_questions, f'global_p_{group}')
                    for group in global_target}
    for group, target in global_target.items():
        count = sum(variable for question, variable in all_variables if _group(question) == group)
        model.Add(global_bloom[group] >= count - target)
        model.Add(global_bloom[group] >= target - count)
    model.Minimize(sum(total_difficulty) + sum(global_bloom.values()))
    solver, outcome, raw_status = _solve(model)
    if solver is None:
        return {'outcome': outcome, 'runtime_s': time.perf_counter() - started,
                'status': raw_status}
    by_id = {question['id']: question for question in bank}
    selected, section_rows, difficulty = {}, [], 0
    for name, (section, pool, variables) in section_data.items():
        ids = [question['id'] for question in pool if solver.Value(variables[question['id']])]
        selected[name] = ids
        section_difficulty = _section_difficulty(ids, by_id, section['difficulty_target'])
        difficulty += section_difficulty
        section_rows.append({'section': name, 'difficulty': section_difficulty,
                             'question_count': section['question_count']})
    bloom_deviation, coverage = _paper_metrics(selected, by_id, chapset)
    return {'outcome': 'feasible', 'difficulty': difficulty, 'bloom_deviation': bloom_deviation,
            'coverage': coverage, 'runtime_s': time.perf_counter() - started, 'sections': selected,
            'section_rows': section_rows, 'status': raw_status}


def _median(values):
    return float(np.median(values)) if values else None


def run_joint_policy_comparison(manifest=None):
    manifest = build_manifest() if manifest is None else manifest
    rows = []
    for blueprint in manifest:
        sequential = evaluate_sequential(blueprint, 'b1')
        joint = solve_joint_lex(blueprint)
        orders = {name: evaluate_sequential(blueprint, 'b1', order)
                  for name, order in ORDERINGS.items()}
        rows.append({'blueprint': blueprint, 'sequential': sequential, 'joint': joint, 'orders': orders})
    comparable = [row for row in rows if row['sequential']['outcome'] == 'feasible'
                  and row['joint']['outcome'] == 'feasible']
    comparison = {}
    for metric in ('difficulty', 'bloom_deviation', 'coverage', 'runtime_s'):
        sequential_values = [row['sequential'][metric] for row in comparable]
        joint_values = [row['joint'][metric] for row in comparable]
        if metric == 'coverage':
            differences = [joint - sequential for joint, sequential in zip(joint_values, sequential_values)]
        else:
            differences = [sequential - joint for sequential, joint in zip(sequential_values, joint_values)]
        comparison[metric] = {'sequential_median': _median(sequential_values),
                              'joint_median': _median(joint_values),
                              'median_difference_joint_favourable': _median(differences),
                              'joint_wins': sum(value > 0 for value in differences),
                              'ties': sum(value == 0 for value in differences),
                              'sequential_wins': sum(value < 0 for value in differences)}
    order_summaries = {}
    for name in ORDERINGS:
        feasible = [row['orders'][name] for row in rows if row['orders'][name]['outcome'] == 'feasible']
        order_summaries[name] = {'feasible_count': len(feasible),
                                 'difficulty_median': _median([row['difficulty'] for row in feasible]),
                                 'bloom_deviation_median': _median([row['bloom_deviation'] for row in feasible]),
                                 'coverage_median': _median([row['coverage'] for row in feasible]),
                                 'runtime_s_median': _median([row['runtime_s'] for row in feasible])}
    counts = Counter((row['sequential']['outcome'], row['joint']['outcome']) for row in rows)
    return {'scheduled_count': len(rows), 'comparable_count': len(comparable),
            'feasibility_transitions': {f'{sequential}->{joint}': count
                                        for (sequential, joint), count in sorted(counts.items())},
            'comparison': comparison, 'order_summaries': order_summaries, 'rows': rows}


def _format(report):
    lines = [f"joint policy comparison: {report['comparable_count']}/{report['scheduled_count']} comparable blueprints",
             'feasibility transitions: ' + ', '.join(f'{key}={value}' for key, value in report['feasibility_transitions'].items()),
             'metric | sequential median | joint median | joint-favourable median difference | joint wins/ties/sequential wins']
    for metric, values in report['comparison'].items():
        lines.append(f"{metric} | {values['sequential_median']} | {values['joint_median']} | "
                     f"{values['median_difference_joint_favourable']} | {values['joint_wins']}/{values['ties']}/{values['sequential_wins']}")
    lines.append('section order summaries:')
    for name, values in report['order_summaries'].items():
        lines.append(f"{name}: feasible={values['feasible_count']}, D={values['difficulty_median']}, "
                     f"Bloom={values['bloom_deviation_median']}, coverage={values['coverage_median']}, "
                     f"solver_s={values['runtime_s_median']}")
    return '\n'.join(lines)


def main():
    result = run_joint_policy_comparison()
    output_path = results_path('results_joint_policy_comparison.json')
    with open(output_path, 'w', encoding='utf-8') as output:
        json.dump(result, output, indent=2)
    print(_format(result))


if __name__ == '__main__':
    main()
