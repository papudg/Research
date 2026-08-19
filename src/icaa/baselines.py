"""
RQ1 comparison: B0, B0-R (best-of-5 seeds), B2 (weighted-sum), B3 (soft-window), B1 (lexicographic).
Full 80-mark paper, per-section with cross-section uniqueness. Reports paper-level D (per-section sum),
Bloom deviation, coverage, solve time.
"""
from collections import Counter
from itertools import combinations as _comb
import time

from ortools.sat.python import cp_model

from icaa.generate import bloom, chapter, chapters_of, diff, load_bank, solve_b0, solve_b1

BANK = load_bank()
CHAP = chapters_of(BANK)
BYID = {question['id']: question for question in BANK}
RU = {'Remembering', 'Understanding'}
APP = {'Applying'}
AEC = {'Analysing', 'Evaluating', 'Creating'}
SECTIONS = [('A', 20, 20, 1), ('B', 5, 10, 2), ('C', 6, 18, 3), ('D', 4, 20, 5), ('E', 3, 12, 4)]
COVER = sorted(CHAP)


def feasible_W(tier, K):
    pool = [int(question['time']) for question in BANK if int(question['marks']) == tier and chapter(question, CHAP) is not None]
    if len(pool) <= 12:
        return Counter(sum(combo) for combo in _comb(pool, K)).most_common(1)[0][0]
    return K * Counter(pool).most_common(1)[0][0]


def diff_target(K):
    profile = [3, 6, 5, 3, 2, 1, 0]
    total = sum(profile)
    raw = [max(0, round(value * K / total)) for value in profile]
    while sum(raw) < K:
        raw[1] += 1
    while sum(raw) > K:
        for index in range(6, 0, -1):
            if raw[index] > 0:
                raw[index] -= 1
                break
    return {band + 1: raw[band] for band in range(7)}


def bloom_target(K):
    remember = round(0.54 * K)
    apply = round(0.24 * K)
    return {'RU': remember, 'APP': apply, 'AEC': K - remember - apply}


def gin(question, group):
    level = bloom(question)
    return (level in RU) if group == 'RU' else (level in APP) if group == 'APP' else (level in AEC)


def sec_dev(selected, delta):
    band_counts = Counter(diff(BYID[identifier]) for identifier in selected)
    return sum(abs(band_counts.get(band, 0) - delta[band]) for band in delta)


def _core(pool, model, K, M, W, delta, cover, bloom_targets):
    variables = {question['id']: model.NewBoolVar(question['id']) for question in pool}
    model.Add(sum(int(question['marks']) * variables[question['id']] for question in pool) == M)
    model.Add(sum(int(question['time']) * variables[question['id']] for question in pool) == W)
    model.Add(sum(variables[question['id']] for question in pool) == K)
    bands = sorted(delta)
    deviations = {band: model.NewIntVar(0, K, f'u{band}') for band in bands}
    for band in bands:
        band_count = sum(variables[question['id']] for question in pool if diff(question) == band)
        model.Add(deviations[band] >= band_count - delta[band])
        model.Add(deviations[band] >= delta[band] - band_count)
    coverage = {topic: model.NewBoolVar(f'y{topic}') for topic in cover}
    for topic in cover:
        model.Add(coverage[topic] <= sum(variables[question['id']] for question in pool if chapter(question, CHAP) == topic))
    uncovered = len(cover) - sum(coverage[topic] for topic in cover)
    group_names = sorted(bloom_targets)
    bloom_deviations = {group: model.NewIntVar(0, K, f'bg{group}') for group in group_names}
    for group in group_names:
        group_count = sum(variables[question['id']] for question in pool if gin(question, group))
        model.Add(bloom_deviations[group] >= group_count - bloom_targets[group])
        model.Add(bloom_deviations[group] >= bloom_targets[group] - group_count)
    return variables, deviations, bloom_deviations, coverage, uncovered, bands, group_names


def solve_b2(bank, K, M, W, eligible, chapset, delta, cover, bloom_targets, tier=None, exclude=None, wd=1, wc=1, wb=1):
    excluded = set(exclude or [])
    pool = [
        question for question in bank
        if question['id'] not in excluded
        and chapter(question, chapset) in eligible
        and (tier is None or int(question['marks']) == tier)
    ]
    model = cp_model.CpModel()
    variables, deviations, bloom_deviations, _, uncovered, bands, group_names = _core(
        pool, model, K, M, W, delta, cover, bloom_targets)
    model.Minimize(
        wd * sum(deviations[band] for band in bands)
        + wc * uncovered
        + wb * sum(bloom_deviations[group] for group in group_names)
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    solver.parameters.random_seed = 1
    solver.parameters.num_search_workers = 1
    if solver.Solve(model) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    return [question['id'] for question in pool if solver.Value(variables[question['id']])]


def solve_b3(bank, K, M, W, eligible, chapset, delta, cover, bloom_targets, tier=None, exclude=None, eps=1):
    excluded = set(exclude or [])
    pool = [
        question for question in bank
        if question['id'] not in excluded
        and chapter(question, chapset) in eligible
        and (tier is None or int(question['marks']) == tier)
    ]
    model = cp_model.CpModel()
    variables, deviations, bloom_deviations, _, uncovered, bands, group_names = _core(
        pool, model, K, M, W, delta, cover, bloom_targets)
    difficulty_slack = {band: model.NewIntVar(0, K, f'su{band}') for band in bands}
    bloom_slack = {group: model.NewIntVar(0, K, f'sg{group}') for group in group_names}
    for band in bands:
        model.Add(difficulty_slack[band] >= deviations[band] - eps)
    for group in group_names:
        model.Add(bloom_slack[group] >= bloom_deviations[group] - eps)
    model.Minimize(sum(difficulty_slack.values()) + sum(bloom_slack.values()) + uncovered)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 30
    solver.parameters.random_seed = 1
    solver.parameters.num_search_workers = 1
    if solver.Solve(model) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    return [question['id'] for question in pool if solver.Value(variables[question['id']])]


def gen(kind):
    used = set()
    sections = {}
    elapsed = 0.0
    difficulty = 0
    for name, K, M, tier in SECTIONS:
        duration = feasible_W(tier, K)
        delta = diff_target(K)
        bloom_targets = bloom_target(K)
        started = time.time()
        if kind == 'b0':
            selected, _ = solve_b0(BANK, K, M, duration, set(CHAP), CHAP, marks_tier=tier, exclude=used, seed=1)
        elif kind == 'b0r':
            best = None
            for seed in range(1, 6):
                candidate, _ = solve_b0(BANK, K, M, duration, set(CHAP), CHAP, marks_tier=tier, exclude=used, seed=seed)
                if candidate:
                    deviation = sec_dev(candidate, delta)
                    best = (deviation, candidate) if best is None or deviation < best[0] else best
            selected = best[1] if best else None
        elif kind == 'b2':
            selected = solve_b2(BANK, K, M, duration, set(CHAP), CHAP, delta, COVER, bloom_targets, tier=tier, exclude=used)
        elif kind == 'b3':
            selected = solve_b3(BANK, K, M, duration, set(CHAP), CHAP, delta, COVER, bloom_targets, tier=tier, exclude=used)
        elif kind == 'b1':
            result, _ = solve_b1(BANK, K, M, duration, set(CHAP), CHAP, delta, COVER, bloom_targets, marks_tier=tier, exclude=used)
            selected = result['sel'] if result else None
        elapsed += time.time() - started
        if selected is None:
            print(f"  {kind} section {name}: INFEASIBLE")
            return None
        sections[name] = selected
        used |= set(selected)
        difficulty += sec_dev(selected, delta)
    return sections, elapsed, difficulty


def metrics(sections):
    identifiers = [identifier for section in sections.values() for identifier in section]
    bloom_counts = Counter(bloom(BYID[identifier]) for identifier in identifiers)
    groups = {
        'RU': sum(bloom_counts.get(level, 0) for level in RU),
        'APP': sum(bloom_counts.get(level, 0) for level in APP),
        'AEC': sum(bloom_counts.get(level, 0) for level in AEC),
    }
    question_count = len(identifiers)
    targets = bloom_target(question_count)
    bloom_deviation = sum(abs(groups[group] - targets[group]) for group in targets)
    coverage = len(set(chapter(BYID[identifier], CHAP) for identifier in identifiers))
    return bloom_deviation, coverage, groups, targets


def main():
    print("=== RQ1: full 80-mark paper, 5 methods (475-item bank) ===")
    print(f"{'method':8s} {'D':>4s} {'bloom_dev':>10s} {'coverage':>9s} {'bloom(RU/APP/AEC)':>20s} {'time(s)':>8s}")
    for kind, label in [('b0', 'B0'), ('b0r', 'B0-R'), ('b2', 'B2'), ('b3', 'B3'), ('b1', 'B1')]:
        output = gen(kind)
        if output is None:
            print(f"{label:8s} FAILED")
            continue
        sections, elapsed, difficulty = output
        bloom_deviation, coverage, groups, _ = metrics(sections)
        print(f"{label:8s} {difficulty:4d} {bloom_deviation:10d} {coverage:>4d}/7     {str(groups):>20s} {elapsed:8.2f}")
    print("  target bloom (54/24/22 of 38):", bloom_target(38))


if __name__ == '__main__':
    main()
