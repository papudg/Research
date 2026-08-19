"""
Beyond Feasibility — CP-SAT solvers and item-bank utilities.

Replicates deployed B0 (first-feasible) and implements B1 (three-pass lexicographic).
Reads the static 475-item fixture; no live database connection.
"""
import itertools
import json
import time
from pathlib import Path

from ortools.sat.python import cp_model

from icaa.paths import BANK_REL, resolve_bank_path

BLOOM = ['Remembering', 'Understanding', 'Applying', 'Analysing', 'Evaluating', 'Creating']
RU, APP, AEC = {'Remembering', 'Understanding'}, {'Applying'}, {'Analysing', 'Evaluating', 'Creating'}
BANK_PATH = BANK_REL.as_posix()


def load_bank(path: str | Path | None = None):
    bank_file = resolve_bank_path(path)
    with open(bank_file, encoding='utf-8') as handle:
        bank = json.load(handle)
    for question in bank:
        question['tags'] = [tag.strip() for tag in question.get('tags', []) if isinstance(tag, str)]
    return bank


def chapters_of(bank):
    skip = set(BLOOM) | {'CBSE2025', 'MCQ', 'SA', 'LA', 'VSA'}
    out = set()
    for question in bank:
        for tag in question['tags']:
            if tag in skip or tag.startswith('case_study') or tag.startswith('SQP') or tag.startswith('assertion_reasoning'):
                continue
            out.add(tag)
    return out


def chapter(question, chapset):
    for tag in question['tags']:
        if tag in chapset:
            return tag
    return None


def bloom(question):
    for tag in question['tags']:
        if tag in BLOOM:
            return tag
    return None


def diff(question):
    return int(question['difficulty'])


def solve_b0(bank, K, M, W, eligible_chaps, chapset, conflict=None, seed_ids=None, marks_tier=None, exclude=None, seed=1):
    model = cp_model.CpModel()
    excluded = set(exclude or [])
    pool = [
        question for question in bank
        if question['id'] not in excluded
        and chapter(question, chapset) in eligible_chaps
        and (marks_tier is None or int(question['marks']) == marks_tier)
    ]
    if seed_ids is not None:
        allowed = set(seed_ids)
        pool = [question for question in pool if question['id'] in allowed]
    variables = {question['id']: model.NewBoolVar(question['id']) for question in pool}
    model.Add(sum(int(question['marks']) * variables[question['id']] for question in pool) == M)
    model.Add(sum(int(question['time']) * variables[question['id']] for question in pool) == W)
    model.Add(sum(variables[question['id']] for question in pool) == K)
    if conflict:
        for left, right in conflict:
            if left in variables and right in variables:
                model.Add(variables[left] + variables[right] <= 1)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    solver.parameters.random_seed = seed
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return [question['id'] for question in pool if solver.Value(variables[question['id']])], status
    return None, status


def solve_b1(bank, K, M, W, eligible_chaps, chapset, delta, cover_topics, bloom_target_groups, marks_tier=None, exclude=None):
    excluded = set(exclude or [])
    pool = [
        question for question in bank
        if question['id'] not in excluded
        and chapter(question, chapset) in eligible_chaps
        and (marks_tier is None or int(question['marks']) == marks_tier)
    ]
    model = cp_model.CpModel()
    variables = {question['id']: model.NewBoolVar(question['id']) for question in pool}
    model.Add(sum(int(question['marks']) * variables[question['id']] for question in pool) == M)
    model.Add(sum(int(question['time']) * variables[question['id']] for question in pool) == W)
    model.Add(sum(variables[question['id']] for question in pool) == K)
    bands = sorted(set(delta.keys()))
    deviations = {band: model.NewIntVar(0, K, f'u{band}') for band in bands}
    for band in bands:
        count = sum(variables[question['id']] for question in pool if diff(question) == band)
        model.Add(deviations[band] >= count - delta[band])
        model.Add(deviations[band] >= delta[band] - count)
    model.Minimize(sum(deviations[band] for band in bands))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    solver.parameters.random_seed = 1
    solver.parameters.num_search_workers = 1
    status1 = solver.Solve(model)
    if status1 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, 'infeasible'
    d_star = round(solver.ObjectiveValue())
    model.Add(sum(deviations[band] for band in bands) <= d_star)
    coverage = {topic: model.NewBoolVar(f'y{topic}') for topic in cover_topics}
    for topic in cover_topics:
        model.Add(coverage[topic] <= sum(variables[question['id']] for question in pool if chapter(question, chapset) == topic))
    model.Maximize(sum(coverage[topic] for topic in cover_topics))
    solver2 = cp_model.CpSolver()
    solver2.parameters.max_time_in_seconds = 30
    solver2.parameters.random_seed = 1
    solver2.parameters.num_search_workers = 1
    status2 = solver2.Solve(model)
    if status2 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, 'infeasible2'
    c_star = round(solver2.ObjectiveValue())
    model.Add(sum(coverage[topic] for topic in cover_topics) >= c_star)
    group_names = sorted(bloom_target_groups.keys())
    bloom_deviations = {group: model.NewIntVar(0, K, f'ub{group}') for group in group_names}

    def group_in(question, group):
        level = bloom(question)
        return (level in RU) if group == 'RU' else (level in APP) if group == 'APP' else (level in AEC)

    for group in group_names:
        count = sum(variables[question['id']] for question in pool if group_in(question, group))
        model.Add(bloom_deviations[group] >= count - bloom_target_groups[group])
        model.Add(bloom_deviations[group] >= bloom_target_groups[group] - count)
    model.Maximize(-sum(bloom_deviations[group] for group in group_names))
    solver3 = cp_model.CpSolver()
    solver3.parameters.max_time_in_seconds = 30
    solver3.parameters.random_seed = 1
    solver3.parameters.num_search_workers = 1
    status3 = solver3.Solve(model)
    if status3 not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, 'infeasible3'
    selected = [question['id'] for question in pool if solver3.Value(variables[question['id']])]
    return {
        'sel': selected,
        'Dstar': d_star,
        'Cstar': c_star,
        'bloom_dev': round(-solver3.ObjectiveValue()),
        'pass_statuses': [str(status1), str(status2), str(status3)],
    }, 'ok'


def hist(ids, byid, key):
    counts = {}
    for identifier in ids:
        counts[key(byid[identifier])] = counts.get(key(byid[identifier]), 0) + 1
    return counts


def report(name, ids, byid, chapset, delta, cover, bloom_target_groups):
    if not ids:
        print(f"{name}: INFEASIBLE")
        return
    difficulty = sum(abs(hist(ids, byid, diff).get(band, 0) - delta.get(band, 0)) for band in delta)
    covered = sorted(set(chapter(byid[identifier], chapset) for identifier in ids))
    coverage_score = len([topic for topic in cover if topic in covered])
    bloom_counts = hist(ids, byid, bloom)

    def group_count(group):
        return sum(bloom_counts.get(level, 0) for level in (RU if group == 'RU' else APP if group == 'APP' else AEC))

    bloom_dev = sum(abs(group_count(group) - bloom_target_groups[group]) for group in bloom_target_groups)
    print(f"\n{name}: {len(ids)} Q  | D(difficulty dev)={difficulty}  coverage={coverage_score}/{len(cover)}  bloom_dev={bloom_dev}")
    print("   difficulty hist:", {band: hist(ids, byid, diff).get(band, 0) for band in sorted(delta)})
    print("   bloom:", {group: group_count(group) for group in bloom_target_groups}, " target:", bloom_target_groups)
    print("   chapters:", covered)


def chapter2(question, chapset):
    for tag in question['tags']:
        if tag in chapset:
            return tag
    return None


def toy_check():
    toy = [
        {'id': f'q{index + 1}', 'marks': marks, 'time': 1, 'difficulty': difficulty, 'tags': [topic]}
        for index, (marks, difficulty, topic) in enumerate([
            (2, 1, 'Algebra'), (2, 1, 'Geometry'), (3, 1, 'Trig'), (3, 1, 'Algebra'),
            (3, 2, 'Geometry'), (3, 2, 'Trig'), (5, 3, 'Algebra'), (5, 3, 'Calc'),
        ])
    ]
    chapset = set(topic for _, _, topic in [
        (2, 1, 'Algebra'), (2, 1, 'Geometry'), (3, 1, 'Trig'), (3, 1, 'Algebra'),
        (3, 2, 'Geometry'), (3, 2, 'Trig'), (5, 3, 'Algebra'), (5, 3, 'Calc'),
    ])
    marks_total, question_count = 10, 4
    delta = {1: 2, 2: 2, 3: 0}
    cover = ['Algebra', 'Geometry', 'Trig']
    best = None
    for size in range(len(toy) + 1):
        for combo in itertools.combinations(toy, size):
            if len(combo) != question_count or sum(question['marks'] for question in combo) != marks_total:
                continue
            if sum(question['time'] for question in combo) != 4:
                continue
            deviation = sum(abs(sum(1 for question in combo if question['difficulty'] == band) - delta[band]) for band in delta)
            coverage = len(set(chapter2(question, chapset) for question in combo))
            key = (deviation, -coverage)
            if best is None or key < best[0]:
                best = (key, combo)
    brute_force = best[1]
    result, status = solve_b1(toy, question_count, marks_total, 4, set(chapset), chapset, delta, cover, {'RU': 0, 'APP': 0, 'AEC': 0})
    brute_d = sum(abs(sum(1 for question in brute_force if question['difficulty'] == band) - delta[band]) for band in delta)
    brute_c = len(set(chapter2(question, chapset) for question in brute_force))
    print("TOY brute-force: D=%d C=%d ids=%s" % (brute_d, brute_c, [question['id'] for question in brute_force]))
    if result is None:
        print("TOY CP-SAT  B1 : None (status %s)" % status)
        ok = False
    else:
        print("TOY CP-SAT  B1 : D=%d C=%d ids=%s" % (result['Dstar'], result['Cstar'], result['sel']))
        ok = brute_d == result['Dstar'] and brute_c == result['Cstar']
    print("CORRECTNESS CHECK:", "PASS" if ok else "FAIL")


def real_run():
    from collections import Counter

    bank = load_bank()
    chapset = chapters_of(bank)
    byid = {question['id']: question for question in bank}
    print("\n=== Real generation on final 475-item Class X bank ===")
    print("chapters discovered:", sorted(chapset))
    one_mark = [question for question in bank if int(question['marks']) == 1]
    time_mode = Counter(int(question['time']) for question in one_mark).most_common(1)[0][0]
    question_count, marks_total = 20, 20
    duration = question_count * time_mode
    print(
        "1-mark pool:", len(one_mark), "| time mode:", time_mode, "-> W=", duration,
        "| time dist:", dict(sorted(Counter(int(question['time']) for question in one_mark).items())),
    )
    eligible = set(chapset)
    cover = [
        'ALGEBRA', 'GEOMETRY', 'TRIGONOMETRY', 'NUMBER_SYSTEMS', 'MENSURATION',
        'STATISTICS_PROBABILTY', 'COORDINATE_GEOMETRY',
    ]
    delta = {1: 3, 2: 6, 3: 5, 4: 3, 5: 2, 6: 1, 7: 0}
    bloom_target_groups = {'RU': 11, 'APP': 5, 'AEC': 4}
    started = time.time()
    baseline, status0 = solve_b0(bank, question_count, marks_total, duration, eligible, chapset)
    baseline_time = time.time() - started
    started = time.time()
    optimized, status1 = solve_b1(bank, question_count, marks_total, duration, eligible, chapset, delta, cover, bloom_target_groups)
    optimized_time = time.time() - started
    print(f"\nB0 status={status0} ({baseline_time:.2f}s) | B1 status={status1} ({optimized_time:.2f}s)")
    if optimized:
        report("B0 first-feasible", baseline, byid, chapset, delta, cover, bloom_target_groups)
    report("B1 lexicographic ", optimized['sel'] if optimized else None, byid, chapset, delta, cover, bloom_target_groups)
    if baseline:
        print("   B0 sample ids:", baseline[:6])
    if optimized:
        print("   B1 sample ids:", optimized['sel'][:6])


def main():
    print("=== Phase A: brute-force correctness check (running example) ===")
    toy_check()
    real_run()


if __name__ == '__main__':
    main()
