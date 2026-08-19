"""Deterministic shared RQ1 blueprint suite for B0, BG, B1, B2, and B3."""
import random
import time
from collections import Counter

from icaa.baselines import BANK, CHAP, COVER, SECTIONS, _core, bloom_target, feasible_W, gin, metrics, sec_dev
from icaa.generate import bloom, chapter, cp_model, diff, solve_b0, solve_b1

POLICIES = ('b0', 'bg', 'b1', 'b2', 'b3')


def _random_delta(question_count, rng):
    weights = [4, 5, 4, 3, 2, 1, 0.3]
    values = [rng.random() * weight for weight in weights]
    total = sum(values)
    counts = [int(question_count * value / total) for value in values]
    index = 0
    while sum(counts) < question_count:
        counts[index % len(counts)] += 1
        index += 1
    while sum(counts) > question_count:
        index = rng.randrange(len(counts))
        if counts[index]:
            counts[index] -= 1
    return {band + 1: counts[band] for band in range(7)}


def build_manifest(seed=42, count=80):
    """Return an immutable-in-practice blueprint protocol shared by all policies."""
    rng = random.Random(seed)
    chapters = sorted(CHAP)
    manifest = []
    for index in range(count):
        eligible = sorted(rng.sample(chapters, rng.randint(5, 7)))
        sections = []
        for name, question_count, marks, tier in SECTIONS:
            sections.append({
                'name': name,
                'question_count': question_count,
                'marks': marks,
                'tier': tier,
                'time': feasible_W(tier, question_count),
                'difficulty_target': _random_delta(question_count, rng),
                'bloom_target': bloom_target(question_count),
            })
        manifest.append({'id': f'blueprint-{index + 1:02d}', 'eligible_chapters': eligible, 'sections': sections})
    return manifest


def impossible_blueprint():
    return {
        'id': 'impossible',
        'eligible_chapters': [],
        'sections': [{'name': 'X', 'question_count': 1, 'marks': 999, 'tier': 1, 'time': 999,
                      'difficulty_target': {1: 1}, 'bloom_target': {'RU': 1, 'APP': 0, 'AEC': 0}}],
    }


def _status_name(status):
    return str(status)


def _classify(status):
    name = _status_name(status).upper()
    if 'INFEASIBLE' in name:
        return 'infeasible'
    if 'UNKNOWN' in name:
        return 'unknown'
    return 'error'


def _pool(eligible, tier, excluded):
    excluded = set(excluded)
    return [question for question in BANK if question['id'] not in excluded and chapter(question, CHAP) in eligible and int(question['marks']) == tier]


def _selected(pool, solver, variables):
    return [question['id'] for question in pool if solver.Value(variables[question['id']])]


def _solve_bg(question_count, marks, duration, eligible, delta, bloom_target_values, tier, excluded):
    pool = _pool(eligible, tier, excluded)
    model = cp_model.CpModel()
    variables = {question['id']: model.NewBoolVar(question['id']) for question in pool}
    model.Add(sum(int(question['marks']) * variables[question['id']] for question in pool) == marks)
    model.Add(sum(int(question['time']) * variables[question['id']] for question in pool) == duration)
    model.Add(sum(variables[question['id']] for question in pool) == question_count)
    deficits = dict(delta)
    for question in sorted(pool, key=lambda item: -deficits.get(diff(item), 0))[:question_count]:
        model.AddHint(variables[question['id']], 1)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    solver.parameters.random_seed = 1
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, status
    return _selected(pool, solver, variables), status


def _solve_b2(question_count, marks, duration, eligible, delta, bloom_target_values, tier, excluded, weights=(1, 1, 1)):
    pool = _pool(eligible, tier, excluded)
    model = cp_model.CpModel()
    variables, deviations, bloom_deviations, coverage, uncovered, bands, groups = _core(
        pool, model, question_count, marks, duration, delta, COVER, bloom_target_values)
    alpha, beta, gamma = weights
    model.Minimize(alpha * sum(deviations[band] for band in bands) + beta * uncovered + gamma * sum(bloom_deviations[group] for group in groups))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    solver.parameters.random_seed = 1
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, status
    return _selected(pool, solver, variables), status


def _solve_b3(question_count, marks, duration, eligible, delta, bloom_target_values, tier, excluded):
    pool = _pool(eligible, tier, excluded)
    model = cp_model.CpModel()
    variables, deviations, bloom_deviations, coverage, uncovered, bands, groups = _core(
        pool, model, question_count, marks, duration, delta, COVER, bloom_target_values)
    difficulty_slack = {band: model.NewIntVar(0, question_count, f'su{band}') for band in bands}
    bloom_slack = {group: model.NewIntVar(0, question_count, f'sg{group}') for group in groups}
    for band in bands:
        model.Add(difficulty_slack[band] >= deviations[band] - 1)
    for group in groups:
        model.Add(bloom_slack[group] >= bloom_deviations[group] - 1)
    model.Minimize(sum(difficulty_slack.values()) + sum(bloom_slack.values()) + uncovered)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    solver.parameters.random_seed = 1
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, status
    return _selected(pool, solver, variables), status


def _run_section(policy, section, eligible, excluded, blueprint_index):
    arguments = (section['question_count'], section['marks'], section['time'], eligible,
                 section['difficulty_target'], section['bloom_target'], section['tier'], excluded)
    if policy == 'b0':
        return solve_b0(BANK, section['question_count'], section['marks'], section['time'], eligible, CHAP,
                        marks_tier=section['tier'], exclude=excluded, seed=blueprint_index + 1)
    if policy == 'bg':
        return _solve_bg(*arguments)
    if policy == 'b1':
        result, status = solve_b1(BANK, section['question_count'], section['marks'], section['time'], eligible, CHAP,
                                  section['difficulty_target'], COVER, section['bloom_target'],
                                  marks_tier=section['tier'], exclude=excluded)
        return (result['sel'] if result else None), status
    if policy == 'b2':
        return _solve_b2(*arguments)
    if policy == 'b3':
        return _solve_b3(*arguments)
    raise ValueError(f'unknown policy: {policy}')


def evaluate_blueprint(blueprint, policy, weights=(1, 1, 1)):
    if policy not in POLICIES:
        raise ValueError(f'unknown policy: {policy}')
    eligible = set(blueprint['eligible_chapters'])
    selected = {}
    section_statuses = []
    difficulty = 0
    runtime = 0.0
    used = set()
    suffix = blueprint['id'].rsplit('-', 1)[-1]
    blueprint_index = int(suffix) if suffix.isdigit() else 1
    for raw_section in blueprint['sections']:
        section = dict(raw_section)
        section['difficulty_target'] = {int(band): value for band, value in raw_section['difficulty_target'].items()}
        started = time.perf_counter()
        if policy == 'b2' and weights != (1, 1, 1):
            ids, status = _solve_b2(section['question_count'], section['marks'], section['time'], eligible,
                                     section['difficulty_target'], section['bloom_target'], section['tier'], used, weights)
        else:
            ids, status = _run_section(policy, section, eligible, used, blueprint_index)
        runtime += time.perf_counter() - started
        section_statuses.append({'section': section['name'], 'status': _status_name(status)})
        if ids is None:
            return {'outcome': _classify(status), 'difficulty': None, 'bloom_deviation': None,
                    'coverage': None, 'runtime_s': runtime, 'section_statuses': section_statuses}
        selected[section['name']] = ids
        used.update(ids)
        difficulty += sec_dev(ids, section['difficulty_target'])
    bloom_deviation, coverage, _, _ = metrics(selected)
    return {'outcome': 'feasible', 'difficulty': difficulty, 'bloom_deviation': bloom_deviation,
            'coverage': coverage, 'runtime_s': runtime, 'section_statuses': section_statuses,
            'sections': selected}


def run_suite():
    manifest = build_manifest()
    rows = []
    for blueprint in manifest:
        outcomes = {policy: evaluate_blueprint(blueprint, policy) for policy in POLICIES}
        rows.append({'blueprint': blueprint, 'outcomes': outcomes})
    common = [row['blueprint']['id'] for row in rows if all(row['outcomes'][policy]['outcome'] == 'feasible' for policy in POLICIES)]
    return {'manifest': manifest, 'rows': rows, 'common_feasible_ids': common}
