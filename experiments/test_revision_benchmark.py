import unittest

from revision_benchmark import (
    choose_constructive_local,
    holm_adjust,
    section_is_valid,
    solve_direct_compliance,
    solve_lex_components,
    solve_b1_candidates,
    residual_flexibility_score,
)
from joint_policy_comparison import solve_joint_direct_compliance, solve_joint_lex
from multipolicy_benchmark import build_manifest


class RevisionBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.chapter_set = {'Algebra'}
        self.bank = [
            {'id': 'a', 'marks': 1, 'time': 1, 'difficulty': 1, 'tags': ['Algebra', 'Remembering']},
            {'id': 'b', 'marks': 1, 'time': 1, 'difficulty': 2, 'tags': ['Algebra', 'Understanding']},
            {'id': 'c', 'marks': 1, 'time': 2, 'difficulty': 2, 'tags': ['Algebra', 'Applying']},
            {'id': 'd', 'marks': 1, 'time': 2, 'difficulty': 3, 'tags': ['Algebra', 'Applying']},
        ]
        self.delta = {1: 1, 2: 1, 3: 0}
        self.bloom_target = {'RU': 1, 'APP': 1, 'AEC': 0}

    def test_constructive_local_returns_a_hard_valid_selection(self):
        ids = choose_constructive_local(
            self.bank, 2, 2, 3, {'Algebra'}, self.chapter_set, self.delta,
            ['Algebra'], self.bloom_target, tier=1, seed=7,
        )
        self.assertIsNotNone(ids)
        self.assertTrue(section_is_valid(self.bank, ids, 2, 2, 3))

    def test_constructive_local_respects_conflict_edges(self):
        ids = choose_constructive_local(
            self.bank, 2, 2, 3, {'Algebra'}, self.chapter_set, self.delta,
            ['Algebra'], self.bloom_target, tier=1, seed=7, conflict=[('a', 'c')],
        )
        self.assertIsNotNone(ids)
        self.assertFalse({'a', 'c'}.issubset(ids))

    def test_direct_and_lex_variants_return_hard_valid_selections(self):
        for solver in (solve_direct_compliance,):
            ids, status = solver(
                self.bank, 2, 2, 3, {'Algebra'}, self.chapter_set, self.delta,
                ['Algebra'], self.bloom_target, tier=1,
            )
            self.assertEqual('feasible', status)
            self.assertTrue(section_is_valid(self.bank, ids, 2, 2, 3))
        for components in (('D',), ('D', 'C'), ('D', 'C', 'P'), ('C', 'P')):
            ids, status = solve_lex_components(
                self.bank, 2, 2, 3, {'Algebra'}, self.chapter_set, self.delta,
                ['Algebra'], self.bloom_target, tier=1, components=components,
            )
            self.assertEqual('feasible', status)
            self.assertTrue(section_is_valid(self.bank, ids, 2, 2, 3))

    def test_b1_candidate_generation_returns_distinct_hard_valid_candidates(self):
        candidates, status = solve_b1_candidates(
            self.bank, 1, 1, 1, {'Algebra'}, self.chapter_set,
            {1: 0, 2: 0, 3: 0}, ['Algebra'], self.bloom_target,
            tier=1, k=3, epsilon=0,
        )
        self.assertEqual('feasible', status)
        self.assertGreaterEqual(len(candidates), 2)
        ids = [tuple(candidate['ids']) for candidate in candidates]
        self.assertEqual(len(ids), len(set(ids)))
        for candidate in candidates:
            self.assertTrue(section_is_valid(self.bank, candidate['ids'], 1, 1, 1))

    def test_residual_flexibility_support_and_conflict_terms_are_bounded(self):
        section = {
            'question_count': 1, 'time': 1, 'tier': 1,
            'difficulty_target': {1: 1, 2: 0, 3: 0},
            'bloom_target': {'RU': 1, 'APP': 0, 'AEC': 0},
        }
        score = residual_flexibility_score(
            self.bank, [section], {'Algebra'}, self.chapter_set, ['Algebra'],
            conflict=[('a', 'b'), ('a', 'c'), ('a', 'd')],
        )
        # Exact reachability contributes +100; the four normalized terms lie
        # in [-1, 3], so the complete one-section score is in [99, 103].
        self.assertGreaterEqual(score, 99.0)
        self.assertLessEqual(score, 103.0)

    def test_holm_adjustment_is_monotone_and_bounded(self):
        adjusted = holm_adjust([0.001, 0.02, 0.04, 0.8])
        self.assertEqual(4, len(adjusted))
        self.assertTrue(all(0 <= value <= 1 for value in adjusted))
        self.assertEqual(sorted(adjusted), adjusted)

    def test_manifest_seeds_are_repeatable_and_independent(self):
        self.assertEqual(build_manifest(seed=43, count=3), build_manifest(seed=43, count=3))
        self.assertNotEqual(build_manifest(seed=42, count=3), build_manifest(seed=43, count=3))

    def test_joint_lex_enforces_cross_section_item_uniqueness(self):
        blueprint = {
            'id': 'toy-01', 'eligible_chapters': ['Algebra'], 'sections': [
                {'name': 'A', 'question_count': 1, 'marks': 1, 'time': 1, 'tier': 1,
                 'difficulty_target': {1: 1, 2: 0, 3: 0}, 'bloom_target': self.bloom_target},
                {'name': 'B', 'question_count': 1, 'marks': 1, 'time': 2, 'tier': 1,
                 'difficulty_target': {1: 0, 2: 1, 3: 0}, 'bloom_target': self.bloom_target},
            ],
        }
        result = solve_joint_lex(blueprint, bank=self.bank, chapset=self.chapter_set, cover_topics=['Algebra'])
        self.assertEqual('feasible', result['outcome'])
        self.assertTrue(set(result['sections']['A']).isdisjoint(result['sections']['B']))
        direct = solve_joint_direct_compliance(blueprint, bank=self.bank, chapset=self.chapter_set)
        self.assertEqual('feasible', direct['outcome'])
        self.assertTrue(set(direct['sections']['A']).isdisjoint(direct['sections']['B']))


if __name__ == '__main__':
    unittest.main()
