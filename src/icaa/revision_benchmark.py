"""Independent baselines and reusable helpers for the major-revision evidence."""
from __future__ import annotations

import random
import time
from collections import Counter

from icaa.baselines import AEC, APP, BANK, BYID, CHAP, COVER, RU, gin, metrics, sec_dev
from icaa.generate import bloom, chapter, cp_model, diff, solve_b0, solve_b1


def _pool(bank, eligible, chapset, tier, excluded=()):
    excluded = set(excluded)
    return [
        question for question in bank
        if question['id'] not in excluded
        and chapter(question, chapset) in eligible
        and (tier is None or int(question['marks']) == tier)
    ]


def _group(question):
    level = bloom(question)
    if level in RU:
        return 'RU'
    if level in APP:
        return 'APP'
    if level in AEC:
        return 'AEC'
    return None


def section_is_valid(bank, ids, question_count, marks, duration):
    if ids is None or len(ids) != question_count or len(set(ids)) != len(ids):
        return False
    by_id = {question['id']: question for question in bank}
    if any(identifier not in by_id for identifier in ids):
        return False
    selected = [by_id[identifier] for identifier in ids]
    return (sum(int(question['marks']) for question in selected) == marks
            and sum(int(question['time']) for question in selected) == duration)


def _completion_possible(pool, question_count, duration):
    if question_count == 0:
        return duration == 0
    if question_count < 0 or duration < 0:
        return False
    reachable = {(0, 0)}
    for question in pool:
        item_time = int(question['time'])
        for count, elapsed in list(reachable):
            if count < question_count and elapsed + item_time <= duration:
                reachable.add((count + 1, elapsed + item_time))
    return (question_count, duration) in reachable


def _selection_scores(selected, delta, cover_topics, bloom_target_groups, chapset):
    by_band = Counter(diff(question) for question in selected)
    by_group = Counter(_group(question) for question in selected)
    covered = {chapter(question, chapset) for question in selected}
    difficulty = sum(abs(by_band.get(band, 0) - target) for band, target in delta.items())
    bloom_deviation = sum(abs(by_group.get(group, 0) - target)
                          for group, target in bloom_target_groups.items())
    coverage = len(set(cover_topics) & covered)
    return difficulty, bloom_deviation, coverage


def choose_constructive_local(bank, question_count, marks, duration, eligible, chapset,
                              delta, cover_topics, bloom_target_groups, tier=None,
                              excluded=(), seed=1, conflict=()):
    pool = _pool(bank, eligible, chapset, tier, excluded)
    conflict_map = {}
    pool_ids = {question['id'] for question in pool}
    for left, right in conflict:
        if left in pool_ids and right in pool_ids:
            conflict_map.setdefault(left, set()).add(right)
            conflict_map.setdefault(right, set()).add(left)
    rng = random.Random(seed)
    states = {(0, 0): (0.0, ())}
    for question in pool:
        item_time = int(question['time'])
        group = _group(question)
        priority = (100 * delta.get(diff(question), 0)
                    + 10 * bloom_target_groups.get(group, 0)
                    + int(chapter(question, chapset) in cover_topics)
                    + rng.random() * 1e-6)
        for (count, elapsed), (score, ids) in list(states.items()):
            next_state = count + 1, elapsed + item_time
            if count >= question_count or elapsed + item_time > duration:
                continue
            if conflict_map.get(question['id'], set()) & set(ids):
                continue
            candidate = score + priority, ids + (question['id'],)
            if (next_state not in states
                    or candidate[0] > states[next_state][0]
                    or (candidate[0] == states[next_state][0] and candidate[1] < states[next_state][1])):
                states[next_state] = candidate
    seed_solution = states.get((question_count, duration))
    if seed_solution is None:
        return None
    by_id = {question['id']: question for question in pool}
    selected = [by_id[identifier] for identifier in seed_solution[1]]
    remaining = [question for question in pool if question['id'] not in seed_solution[1]]
    for _ in range(100):
        current = _selection_scores(selected, delta, cover_topics, bloom_target_groups, chapset)
        current_key = (current[0], current[1], -current[2])
        replacement = None
        for selected_index, old in enumerate(selected):
            for candidate in sorted(remaining, key=lambda question: question['id']):
                if int(candidate['time']) != int(old['time']):
                    continue
                proposal = list(selected)
                proposal[selected_index] = candidate
                proposal_ids = {question['id'] for question in proposal}
                if any(conflict_map.get(question['id'], set()) & (proposal_ids - {question['id']})
                       for question in proposal):
                    continue
                proposal_scores = _selection_scores(proposal, delta, cover_topics, bloom_target_groups, chapset)
                if (proposal_scores[0], proposal_scores[1], -proposal_scores[2]) < current_key:
                    replacement = (selected_index, candidate)
                    break
            if replacement:
                break
        if not replacement:
            break
        index, candidate = replacement
        old = selected[index]
        selected[index] = candidate
        remaining = [question for question in remaining if question['id'] != candidate['id']] + [old]
    ids = [question['id'] for question in selected]
    return ids if section_is_valid(bank, ids, question_count, marks, duration) else None


def _build_cp_model(bank, question_count, marks, duration, eligible, chapset, delta,
                    cover_topics, bloom_target_groups, tier=None, excluded=(), conflict=()):
    pool = _pool(bank, eligible, chapset, tier, excluded)
    model = cp_model.CpModel()
    variables = {question['id']: model.NewBoolVar(question['id']) for question in pool}
    model.Add(sum(int(question['marks']) * variables[question['id']] for question in pool) == marks)
    model.Add(sum(int(question['time']) * variables[question['id']] for question in pool) == duration)
    model.Add(sum(variables[question['id']] for question in pool) == question_count)
    for left, right in conflict:
        if left in variables and right in variables:
            model.Add(variables[left] + variables[right] <= 1)
    deviations = {band: model.NewIntVar(0, question_count, f'd_{band}') for band in delta}
    for band, target in delta.items():
        count = sum(variables[question['id']] for question in pool if diff(question) == band)
        model.Add(deviations[band] >= count - target)
        model.Add(deviations[band] >= target - count)
    coverage = {topic: model.NewBoolVar(f'c_{index}') for index, topic in enumerate(cover_topics)}
    for topic in cover_topics:
        model.Add(coverage[topic] <= sum(variables[question['id']] for question in pool
                                         if chapter(question, chapset) == topic))
    bloom_deviations = {group: model.NewIntVar(0, question_count, f'p_{group}')
                        for group in bloom_target_groups}
    for group, target in bloom_target_groups.items():
        count = sum(variables[question['id']] for question in pool if _group(question) == group)
        model.Add(bloom_deviations[group] >= count - target)
        model.Add(bloom_deviations[group] >= target - count)
    return model, pool, variables, deviations, coverage, bloom_deviations


def _solve(model):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    solver.parameters.random_seed = 1
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return solver, 'feasible'
    if status == cp_model.INFEASIBLE:
        return None, 'infeasible'
    return None, 'unknown'


def _solve_limited(model, max_time=5.0):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time
    solver.parameters.random_seed = 1
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return solver, 'feasible'
    if status == cp_model.INFEASIBLE:
        return None, 'infeasible'
    return None, 'unknown'


def _ids(pool, variables, solver):
    return [question['id'] for question in pool if solver.Value(variables[question['id']])]


def solve_direct_compliance(bank, question_count, marks, duration, eligible, chapset, delta,
                            cover_topics, bloom_target_groups, tier=None, excluded=()):
    model, pool, variables, deviations, _, bloom_deviations = _build_cp_model(
        bank, question_count, marks, duration, eligible, chapset, delta, cover_topics,
        bloom_target_groups, tier, excluded)
    model.Minimize(sum(deviations.values()) + sum(bloom_deviations.values()))
    solver, outcome = _solve(model)
    return (_ids(pool, variables, solver), outcome) if solver else (None, outcome)


def solve_lex_components(bank, question_count, marks, duration, eligible, chapset, delta,
                         cover_topics, bloom_target_groups, tier=None, excluded=(),
                         components=('D', 'C', 'P')):
    allowed = {'D', 'C', 'P'}
    if not components or any(component not in allowed for component in components):
        raise ValueError('components must be a non-empty tuple from D, C, P')
    model, pool, variables, deviations, coverage, bloom_deviations = _build_cp_model(
        bank, question_count, marks, duration, eligible, chapset, delta, cover_topics,
        bloom_target_groups, tier, excluded)
    objectives = {
        'D': (sum(deviations.values()), 'min'),
        'C': (sum(coverage.values()), 'max'),
        'P': (sum(bloom_deviations.values()), 'min'),
    }
    solver = None
    for component in components:
        expression, direction = objectives[component]
        if direction == 'min':
            model.Minimize(expression)
        else:
            model.Maximize(expression)
        solver, outcome = _solve(model)
        if solver is None:
            return None, outcome
        value = round(solver.ObjectiveValue())
        if component == 'D':
            model.Add(expression <= value)
        elif component == 'C':
            model.Add(expression >= value)
        else:
            model.Add(expression <= value)
    return _ids(pool, variables, solver), 'feasible'


def solve_b1_candidates(bank, question_count, marks, duration, eligible, chapset, delta,
                        cover_topics, bloom_target_groups, tier=None, excluded=(), conflict=(),
                        k=3, epsilon=0, max_time=5.0):
    if k < 1 or epsilon < 0:
        raise ValueError('k must be positive and epsilon must be non-negative')
    model, pool, variables, deviations, coverage, bloom_deviations = _build_cp_model(
        bank, question_count, marks, duration, eligible, chapset, delta, cover_topics,
        bloom_target_groups, tier, excluded, conflict)
    difficulty = sum(deviations.values())
    covered = sum(coverage.values())
    bloom_loss = sum(bloom_deviations.values())
    model.Minimize(difficulty)
    solver, status = _solve_limited(model, max_time)
    if solver is None:
        return [], status
    d_star = round(solver.ObjectiveValue())
    model.Add(difficulty <= d_star + epsilon)
    model.Maximize(covered)
    solver, status = _solve_limited(model, max_time)
    if solver is None:
        return [], status
    c_star = round(solver.ObjectiveValue())
    model.Add(covered >= c_star - epsilon)
    model.Minimize(bloom_loss)
    solver, status = _solve_limited(model, max_time)
    if solver is None:
        return [], status
    p_star = round(solver.ObjectiveValue())
    model.Add(bloom_loss <= p_star + epsilon)
    candidates = []
    for _ in range(k):
        solver, status = _solve_limited(model, max_time)
        if solver is None:
            break
        ids = _ids(pool, variables, solver)
        candidates.append({'ids': ids, 'D': round(solver.Value(difficulty)),
                           'C': round(solver.Value(covered)), 'P': round(solver.Value(bloom_loss)),
                           'pass_objectives': {'D': d_star, 'C': c_star, 'P': p_star}})
        model.Add(sum(variables[identifier] for identifier in ids) <= question_count - 1)
    return candidates, 'feasible' if candidates else 'infeasible'


def residual_flexibility_score(bank, remaining_sections, eligible, chapset, cover_topics,
                               used=(), conflict=()):
    """Return a bounded, relaxed downstream-ranking score.

    Each remaining section contributes a reachability term in {-100, +100}
    plus three support fractions and one within-pool conflict-density penalty.
    The latter four terms lie in [-1, 3], so reachability dominates the local
    ranking without making the score a completion count or probability.
    """
    used = set(used)
    conflict_map = {}
    for left, right in conflict:
        conflict_map.setdefault(left, set()).add(right)
        conflict_map.setdefault(right, set()).add(left)
    score = 0.0
    for raw in remaining_sections:
        pool = _pool(bank, eligible, chapset, raw.get('tier'), used)
        count = int(raw['question_count'])
        duration = int(raw['time'])
        if _completion_possible(pool, count, duration):
            score += 100.0
        else:
            score -= 100.0
        target = {int(band): int(value) for band, value in raw['difficulty_target'].items()}
        bloom_target_values = raw['bloom_target']
        pool_size = len(pool)
        pool_scale = float(max(1, pool_size))
        difficulty_support = sum(target.get(diff(question), 0) > 0 for question in pool) / pool_scale
        bloom_support = sum(_group(question) in bloom_target_values and bloom_target_values[_group(question)] > 0
                            for question in pool) / pool_scale
        pool_ids = {question['id'] for question in pool}
        directed_edges = sum(len(conflict_map.get(question['id'], set()) & pool_ids) for question in pool)
        edge_density = directed_edges / float(max(1, pool_size * max(0, pool_size - 1)))
        score += (pool_size / float(max(1, len(bank)))) + difficulty_support + bloom_support - edge_density
    return score


def choose_lookahead_section(bank, section, remaining_sections, eligible, chapset, cover_topics,
                             used=(), conflict=(), k=3, epsilon=0, max_time=5.0):
    delta = {int(band): int(target) for band, target in section['difficulty_target'].items()}
    candidates, status = solve_b1_candidates(
        bank, section['question_count'], section['marks'], section['time'], eligible, chapset,
        delta, cover_topics, section['bloom_target'], tier=section.get('tier'), excluded=used,
        conflict=conflict, k=k, epsilon=epsilon, max_time=max_time)
    if not candidates:
        return None, status, {'candidate_count': 0}
    scored = []
    for candidate in candidates:
        future = residual_flexibility_score(
            bank, remaining_sections, eligible, chapset, cover_topics,
            used=set(used) | set(candidate['ids']), conflict=conflict)
        key = (future, -candidate['D'], candidate['C'], -candidate['P'], tuple(candidate['ids']))
        scored.append((key, future, candidate))
    _, future, selected = max(scored, key=lambda item: item[0])
    return selected['ids'], 'feasible', {
        'candidate_count': len(candidates), 'future_score': future,
        'candidate_objectives': [
            {'D': item[2]['D'], 'C': item[2]['C'], 'P': item[2]['P'], 'future_score': item[1]}
            for item in scored
        ],
    }


def _status_outcome(status):
    text = str(status).upper()
    if 'INFEASIBLE' in text:
        return 'infeasible'
    if 'UNKNOWN' in text:
        return 'unknown'
    return 'error'


def evaluate_sequential(blueprint, policy, order=None, conflict=()):
    section_by_name = {section['name']: section for section in blueprint['sections']}
    names = list(order or [section['name'] for section in blueprint['sections']])
    if set(names) != set(section_by_name) or len(names) != len(section_by_name):
        raise ValueError('order must contain every section exactly once')
    eligible = set(blueprint['eligible_chapters'])
    selected, used, section_rows = {}, set(), []
    runtime, difficulty = 0.0, 0
    lookahead_details = []
    suffix = blueprint['id'].rsplit('-', 1)[-1]
    blueprint_seed = int(suffix) if suffix.isdigit() else 1
    for name in names:
        raw = section_by_name[name]
        section = dict(raw)
        section['difficulty_target'] = {int(band): target for band, target in raw['difficulty_target'].items()}
        started = time.perf_counter()
        if policy == 'local':
            ids = choose_constructive_local(BANK, section['question_count'], section['marks'], section['time'], eligible,
                                            CHAP, section['difficulty_target'], COVER, section['bloom_target'],
                                            tier=section['tier'], excluded=used, seed=blueprint_seed,
                                            conflict=conflict)
            status = 'feasible' if ids else 'heuristic_failure'
        elif policy == 'direct':
            ids, status = solve_direct_compliance(BANK, section['question_count'], section['marks'], section['time'],
                                                  eligible, CHAP, section['difficulty_target'], COVER,
                                                  section['bloom_target'], tier=section['tier'], excluded=used)
        elif policy == 'ablation_d':
            ids, status = solve_lex_components(BANK, section['question_count'], section['marks'], section['time'], eligible,
                                               CHAP, section['difficulty_target'], COVER, section['bloom_target'],
                                               tier=section['tier'], excluded=used, components=('D',))
        elif policy == 'ablation_dc':
            ids, status = solve_lex_components(BANK, section['question_count'], section['marks'], section['time'], eligible,
                                               CHAP, section['difficulty_target'], COVER, section['bloom_target'],
                                               tier=section['tier'], excluded=used, components=('D', 'C'))
        elif policy == 'ablation_dcp':
            ids, status = solve_lex_components(BANK, section['question_count'], section['marks'], section['time'], eligible,
                                               CHAP, section['difficulty_target'], COVER, section['bloom_target'],
                                               tier=section['tier'], excluded=used, components=('D', 'C', 'P'))
        elif policy == 'ablation_cp':
            ids, status = solve_lex_components(BANK, section['question_count'], section['marks'], section['time'], eligible,
                                               CHAP, section['difficulty_target'], COVER, section['bloom_target'],
                                               tier=section['tier'], excluded=used, components=('C', 'P'))
        elif policy == 'b0':
            ids, solver_status = solve_b0(BANK, section['question_count'], section['marks'], section['time'], eligible, CHAP,
                                           marks_tier=section['tier'], exclude=used, seed=blueprint_seed)
            status = 'feasible' if ids else _status_outcome(solver_status)
        elif policy == 'b1':
            result, solver_status = solve_b1(BANK, section['question_count'], section['marks'], section['time'], eligible, CHAP,
                                              section['difficulty_target'], COVER, section['bloom_target'],
                                              marks_tier=section['tier'], exclude=used)
            ids = result['sel'] if result else None
            status = 'feasible' if ids else _status_outcome(solver_status)
        elif policy == 'lookahead':
            future_sections = [section_by_name[future_name] for future_name in names[names.index(name) + 1:]]
            ids, status, details = choose_lookahead_section(
                BANK, section, future_sections, eligible, CHAP, COVER,
                used=used, conflict=conflict, k=3, epsilon=0, max_time=5.0)
            lookahead_details.append({'section': name, **details})
        else:
            raise ValueError(f'unknown revision policy: {policy}')
        elapsed = time.perf_counter() - started
        runtime += elapsed
        section_rows.append({'section': name, 'outcome': status, 'runtime_s': elapsed})
        if not ids:
            return {'outcome': status, 'difficulty': None, 'bloom_deviation': None, 'coverage': None,
                    'runtime_s': runtime, 'section_rows': section_rows,
                    'lookahead': lookahead_details}
        selected[name] = ids
        used.update(ids)
        section_difficulty = sec_dev(ids, section['difficulty_target'])
        difficulty += section_difficulty
        section_rows[-1]['difficulty'] = section_difficulty
    bloom_deviation, coverage, _, _ = metrics(selected)
    return {'outcome': 'feasible', 'difficulty': difficulty, 'bloom_deviation': bloom_deviation,
            'coverage': coverage, 'runtime_s': runtime, 'sections': selected, 'section_rows': section_rows,
            'lookahead': lookahead_details}


def holm_adjust(p_values):
    count = len(p_values)
    adjusted = [None] * count
    running = 0.0
    for rank, index in enumerate(sorted(range(count), key=lambda item: p_values[item])):
        running = max(running, min(1.0, p_values[index] * (count - rank)))
        adjusted[index] = running
    return adjusted
