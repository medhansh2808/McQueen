import unittest

import torch

from mcqueen_ml.training.dataset_v2 import (
    TemporalDrivingDatasetV2,
    build_episode_index,
    compute_driving_stats,
)
from mcqueen_ml.training.model_config_v2 import TemporalPolicyConfig
from mcqueen_ml.training.temporal_policy_v2 import (
    TemporalDrivingPolicy,
    TinyVisualBackbone,
)


class FakeDataset:
    def __init__(self):
        self.rows = []
        for episode in range(2):
            for frame in range(8):
                self.rows.append(
                    {
                        "episode_index": episode,
                        "observation.images.front_rgb": torch.zeros(3, 32, 48),
                        "observation.wheels": torch.tensor(
                            [1.0, frame * 10.0, frame * 11.0]
                        ),
                        "action": torch.tensor(
                            [90.0 + frame, float(frame * 2)]
                        ),
                    }
                )

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        return self.rows[index]


class TemporalPolicyV2Tests(unittest.TestCase):
    def test_dataset_shapes_and_no_target_action_leak(self):
        dataset = FakeDataset()
        episode_map = build_episode_index(dataset)
        train_indices = episode_map[0]
        stats = compute_driving_stats(dataset, train_indices)
        wrapped = TemporalDrivingDatasetV2(
            dataset,
            episode_map,
            episodes=[0],
            stats=stats,
            history=6,
            image_size=(32, 48),
        )

        sample = wrapped[4]
        self.assertEqual(tuple(sample["frames"].shape), (6, 3, 32, 48))
        self.assertEqual(tuple(sample["wheels"].shape), (6, 3))
        self.assertEqual(tuple(sample["previous_actions"].shape), (6, 2))

        # At target frame 4, final previous-action token must be frame-3 action.
        expected = stats.action.normalize(dataset[3]["action"].float())
        self.assertTrue(
            torch.allclose(sample["previous_actions"][-1], expected)
        )
        leaked = stats.action.normalize(dataset[4]["action"].float())
        self.assertFalse(
            torch.allclose(sample["previous_actions"][-1], leaked)
        )

    def test_model_output_shape(self):
        config = TemporalPolicyConfig(
            history=6,
            model_dim=128,
            transformer_layers=2,
            attention_heads=4,
            feedforward_dim=256,
        )
        backbone = TinyVisualBackbone()
        model = TemporalDrivingPolicy(
            backbone,
            visual_dim=backbone.output_dim,
            config=config,
        )

        out = model(
            torch.rand(2, 6, 3, 64, 96),
            torch.rand(2, 6, 3),
            torch.rand(2, 6, 2),
        )
        self.assertEqual(tuple(out.shape), (2, 2))

    def test_rejects_wrong_history(self):
        config = TemporalPolicyConfig(
            history=6,
            model_dim=128,
            transformer_layers=1,
            attention_heads=4,
            feedforward_dim=256,
        )
        backbone = TinyVisualBackbone()
        model = TemporalDrivingPolicy(
            backbone,
            visual_dim=backbone.output_dim,
            config=config,
        )
        with self.assertRaises(ValueError):
            model(
                torch.rand(1, 5, 3, 64, 96),
                torch.rand(1, 5, 3),
                torch.rand(1, 5, 2),
            )


if __name__ == "__main__":
    unittest.main()
