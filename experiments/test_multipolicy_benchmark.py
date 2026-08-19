import unittest

from multipolicy_benchmark import _classify, build_manifest, evaluate_blueprint, impossible_blueprint
from multi_policy_report import aggregate
from weight_sensitivity import weight_grid
from policy_frontier import frontier
from joint_diagnostic import evaluate_joint_feasibility, run_joint_diagnostic


class MultiPolicyBenchmarkTests(unittest.TestCase):
    @staticmethod
    def _toy_blueprint():
        return {'id': 'toy', 'eligible_chapters': ['Algebra'], 'sections': [
            {'name': 'A', 'question_count': 1, 'marks': 1, 'time': 1, 'tier': 1,
             'difficulty_target': {1: 1}, 'bloom_target': {'RU': 1, 'APP': 0, 'AEC': 0}},
            {'name': 'B', 'question_count': 1, 'marks': 1, 'time': 1, 'tier': 1,
             'difficulty_target': {1: 1}, 'bloom_target': {'RU': 1, 'APP': 0, 'AEC': 0}},
        ]}

    @staticmethod
    def _toy_bank():
        return [
            {'id': 'a', 'marks': 1, 'time': 1, 'difficulty': 1, 'tags': ['Algebra', 'Remembering']},
            {'id': 'b', 'marks': 1, 'time': 1, 'difficulty': 1, 'tags': ['Algebra', 'Remembering']},
        ]

    def test_joint_model_finds_a_complete_paper_without_cross_section_reuse(self):
        result = evaluate_joint_feasibility(self._toy_blueprint(), bank=self._toy_bank(), chapset={'Algebra'})

        self.assertEqual('feasible', result['outcome'])
        self.assertTrue(set(result['sections']['A']).isdisjoint(result['sections']['B']))

    def test_joint_model_certifies_a_globally_infeasible_blueprint(self):
        blueprint = self._toy_blueprint()
        blueprint['sections'][1]['question_count'] = 2
        blueprint['sections'][1]['marks'] = 2
        blueprint['sections'][1]['time'] = 2

        result = evaluate_joint_feasibility(blueprint, bank=self._toy_bank(), chapset={'Algebra'})

        self.assertEqual('infeasible', result['outcome'])

    def test_joint_runner_diagnoses_only_sequential_failure_ids(self):
        report = {'failure_events': [{'blueprint_id': 'two'}], 'rows': [
            {'blueprint': dict(self._toy_blueprint(), id='one')},
            {'blueprint': dict(self._toy_blueprint(), id='two')},
        ]}

        result = run_joint_diagnostic(report, bank=self._toy_bank(), chapset={'Algebra'})

        self.assertEqual(['two'], result['diagnosed_ids'])
        self.assertEqual(['two'], [outcome['blueprint_id'] for outcome in result['outcomes']])

    def test_manifest_is_repeatable_and_has_80_blueprints(self):
        self.assertEqual(build_manifest(), build_manifest())
        self.assertEqual(80, len(build_manifest()))

    def test_outcome_contains_explicit_failure_classification(self):
        outcome = evaluate_blueprint(impossible_blueprint(), 'b1')

        self.assertIn(outcome['outcome'], {'infeasible', 'unknown', 'error'})
        self.assertTrue(outcome['section_statuses'])

    def test_lowercase_infeasible_status_is_classified_as_infeasible(self):
        self.assertEqual('infeasible', _classify('infeasible'))

    def test_common_set_and_exclusions_partition_the_manifest(self):
        suite = {
            'manifest': [{'id': 'one'}, {'id': 'two'}],
            'rows': [
                {'blueprint': {'id': 'one'}, 'outcomes': {policy: {'outcome': 'feasible', 'difficulty': 1,
                 'bloom_deviation': 1, 'coverage': 7, 'runtime_s': 0.1} for policy in ('b0', 'bg', 'b1', 'b2', 'b3')}},
                {'blueprint': {'id': 'two'}, 'outcomes': {'b0': {'outcome': 'infeasible'}, 'bg': {'outcome': 'feasible'},
                 'b1': {'outcome': 'feasible'}, 'b2': {'outcome': 'feasible'}, 'b3': {'outcome': 'feasible'}}},
            ],
            'common_feasible_ids': ['one'],
        }
        report = aggregate(suite)
        self.assertEqual(1, report['common_feasible_count'])
        self.assertEqual(1, sum(report['exclusion_counts'].values()))
        self.assertEqual({'feasible': 1, 'infeasible': 1}, report['outcome_counts']['b0'])
        self.assertEqual({'b0', 'bg', 'b1', 'b2', 'b3'}, set(report['medians']))

    def test_weight_grid_has_all_three_weight_axes(self):
        self.assertEqual(27, len(weight_grid()))
        self.assertIn((1, 1, 1), weight_grid())
        self.assertIn((10, 10, 10), weight_grid())

    def test_dominated_solution_is_removed(self):
        points = [
            {'difficulty': 2, 'bloom_deviation': 2, 'coverage': 7, 'runtime_s': 1},
            {'difficulty': 3, 'bloom_deviation': 2, 'coverage': 7, 'runtime_s': 1},
        ]
        self.assertEqual([points[0]], frontier(points))


if __name__ == '__main__':
    unittest.main()
