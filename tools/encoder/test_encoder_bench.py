"""Laptop unit tests for the encoder bench package (no Jetson.GPIO needed).

Run from the repo root:
    python3 -m unittest tools.encoder.test_encoder_bench -v
"""

import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from robot.jetson_nano.mcqueen_edge.gpio_encoder_source import GpioEncoderSource
from tools.encoder import bench_encoder_sweep as bench


class SnapshotContractTest(unittest.TestCase):

    def test_empty_initial_snapshot(self):
        source = GpioEncoderSource(29, 31)
        obs = source.snapshot(0)
        self.assertTrue(obs["encoder_valid"])
        self.assertEqual(obs["left_ticks_total"], 0)
        self.assertEqual(obs["right_ticks_total"], 0)
        self.assertEqual(obs["left_ticks_delta"], 0)
        self.assertEqual(obs["left_ticks_per_s"], 0.0)
        self.assertEqual(obs["sample_dt_s"], 0.0)

    def test_forward_rate_math(self):
        source = GpioEncoderSource(29, 31, count_direction=1)
        source.snapshot(0)
        source._total = 50
        obs = source.snapshot(1000000000)
        self.assertEqual(obs["left_ticks_total"], 50)
        self.assertEqual(obs["right_ticks_total"], 50)
        self.assertEqual(obs["left_ticks_delta"], 50)
        self.assertEqual(obs["right_ticks_delta"], 50)
        self.assertAlmostEqual(obs["left_ticks_per_s"], 50.0)
        self.assertAlmostEqual(obs["sample_dt_s"], 1.0)

    def test_reverse_signed_deltas(self):
        source = GpioEncoderSource(29, 31, count_direction=1)
        source.snapshot(0)
        source._total = 40
        obs = source.snapshot(1500000000)
        self.assertEqual(obs["left_ticks_delta"], 40)
        self.assertEqual(obs["left_ticks_per_s"], 40.0 / 1.5)
        source._total = 30
        obs = source.snapshot(2000000000)
        self.assertEqual(obs["left_ticks_delta"], -10)
        self.assertEqual(obs["left_ticks_per_s"], -20.0)

    def test_invert_direction_flag(self):
        source = GpioEncoderSource(29, 31, count_direction=-1)
        source.snapshot(0)
        source._total = 50
        obs = source.snapshot(1000000000)
        self.assertEqual(obs["left_ticks_delta"], 50)
        self.assertEqual(obs["left_ticks_per_s"], 50.0)

    def test_rpm_conversion(self):
        rate = 100.0
        ticks_per_rev = 50.0
        rpm = rate * 60.0 / ticks_per_rev
        self.assertEqual(rpm, 120.0)


class DutyStepsTest(unittest.TestCase):

    def test_default_range(self):
        args = bench.argparse.Namespace(
            duty_min=0.05, duty_max=0.95, duty_step=0.05)
        steps = bench._duty_steps(args)
        self.assertEqual(steps[0], 0.05)
        self.assertEqual(steps[-1], 0.95)
        self.assertEqual(len(steps), 19)

    def test_single_step(self):
        args = bench.argparse.Namespace(
            duty_min=0.5, duty_max=0.5, duty_step=0.05)
        self.assertEqual(bench._duty_steps(args), [0.5])


class StdTest(unittest.TestCase):

    def test_std(self):
        self.assertAlmostEqual(bench._std([1.0, 2.0, 3.0]), 0.8164965809)
        self.assertEqual(bench._std([]), 0.0)
        self.assertEqual(bench._std([5.0, 5.0]), 0.0)


if __name__ == "__main__":
    unittest.main()