import unittest

from mcqueen_ml.training.temporal_index_v2 import (
    NEUTRAL_ACTION,
    build_temporal_positions,
)


class TemporalIndexTests(unittest.TestCase):
    def test_episode_start_uses_neutral_history(self):
        frames, previous = build_temporal_positions(0, 6)
        self.assertEqual(frames, [0, 0, 0, 0, 0, 0])
        self.assertEqual(previous, [None, None, None, None, None, None])
        self.assertEqual(NEUTRAL_ACTION, (90.0, 0.0))

    def test_second_frame_only_uses_action_zero_at_last_step(self):
        frames, previous = build_temporal_positions(1, 6)
        self.assertEqual(frames, [0, 0, 0, 0, 0, 1])
        self.assertEqual(previous, [None, None, None, None, None, 0])

    def test_normal_window_never_uses_target_action(self):
        frames, previous = build_temporal_positions(8, 6)
        self.assertEqual(frames, [3, 4, 5, 6, 7, 8])
        self.assertEqual(previous, [2, 3, 4, 5, 6, 7])
        self.assertNotIn(8, previous)


if __name__ == "__main__":
    unittest.main()
