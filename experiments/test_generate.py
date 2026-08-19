import os
import subprocess
import sys
import unittest

from baselines import BANK, CHAP, COVER, bloom_target, diff_target, feasible_W
from b1_status_audit import summarize_statuses
from generate import load_bank, solve_b1


class LoadBankPathTests(unittest.TestCase):
    def test_loads_canonical_fixture_when_run_from_experiments_directory(self):
        original = os.getcwd()
        self.addCleanup(os.chdir, original)
        os.chdir(os.path.dirname(__file__))

        self.assertEqual(475, len(load_bank()))

    def test_rq1_policy_rows_are_reproducible(self):
        environment = os.environ | {'PYTHONHASHSEED': '0'}
        command = [sys.executable, 'baselines.py']
        first = subprocess.run(command, cwd=os.path.dirname(__file__), env=environment,
                               check=True, capture_output=True, text=True).stdout
        second = subprocess.run(command, cwd=os.path.dirname(__file__), env=environment,
                                check=True, capture_output=True, text=True).stdout

        def policy_rows(output):
            return [' '.join(line.split()[:-1]) for line in output.splitlines()
                    if line.startswith(('B0 ', 'B0-R ', 'B1 ', 'B2 ', 'B3 '))]

        self.assertEqual(policy_rows(first), policy_rows(second))

    def test_b1_records_each_pass_status(self):
        result, status = solve_b1(BANK, 20, 20, feasible_W(1, 20), set(CHAP), CHAP,
                                  diff_target(20), COVER, bloom_target(20), marks_tier=1)

        self.assertEqual('ok', status)
        self.assertEqual(3, len(result['pass_statuses']))

    def test_b1_status_summary_counts_each_solver_status(self):
        summary = summarize_statuses(['CpSolverStatus.OPTIMAL', 'CpSolverStatus.FEASIBLE',
                                      'CpSolverStatus.OPTIMAL'])

        self.assertEqual({'CpSolverStatus.FEASIBLE': 1, 'CpSolverStatus.OPTIMAL': 2}, summary)


if __name__ == '__main__':
    unittest.main()
