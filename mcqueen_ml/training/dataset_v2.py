"""Episode-safe temporal training dataset for McQueen dataset-v2 conversions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import torch
import torch.nn.functional as F
from torch.utils.data import Dataset

from .temporal_index_v2 import NEUTRAL_ACTION, build_temporal_positions


IMAGE_KEY = "observation.images.front_rgb"
ACTION_KEY = "action"
WHEEL_KEY = "observation.wheels"


@dataclass(frozen=True)
class VectorStats:
    mean: torch.Tensor
    std: torch.Tensor

    def normalize(self, value: torch.Tensor) -> torch.Tensor:
        return (value - self.mean) / self.std

    def denormalize(self, value: torch.Tensor) -> torch.Tensor:
        return value * self.std + self.mean


@dataclass(frozen=True)
class DrivingStats:
    action: VectorStats
    wheel_rates: VectorStats


def _safe_stats(values: torch.Tensor) -> VectorStats:
    mean = values.mean(dim=0)
    std = values.std(dim=0, unbiased=False)
    std = torch.where(std < 1e-6, torch.ones_like(std), std)
    return VectorStats(mean=mean, std=std)


def scalar_int(value) -> int:
    if isinstance(value, torch.Tensor):
        return int(value.item())
    return int(value)


def build_episode_index(dataset) -> dict[int, list[int]]:
    episodes: dict[int, list[int]] = {}
    for dataset_index in range(len(dataset)):
        sample = dataset[dataset_index]
        if "episode_index" not in sample:
            raise KeyError("dataset sample has no episode_index")
        episode = scalar_int(sample["episode_index"])
        episodes.setdefault(episode, []).append(dataset_index)
    return episodes


def compute_driving_stats(dataset, indices: Iterable[int]) -> DrivingStats:
    actions = []
    wheel_rates = []
    for index in indices:
        sample = dataset[index]
        action = torch.as_tensor(sample[ACTION_KEY], dtype=torch.float32)
        wheels = torch.as_tensor(sample[WHEEL_KEY], dtype=torch.float32)
        actions.append(action)
        wheel_rates.append(wheels[1:3])

    if not actions:
        raise ValueError("cannot compute stats from zero samples")

    return DrivingStats(
        action=_safe_stats(torch.stack(actions)),
        wheel_rates=_safe_stats(torch.stack(wheel_rates)),
    )


def prepare_image(image, image_size: tuple[int, int]) -> torch.Tensor:
    image = torch.as_tensor(image, dtype=torch.float32)
    if image.ndim != 3:
        raise ValueError("expected 3D image")
    if image.shape[0] != 3 and image.shape[-1] == 3:
        image = image.permute(2, 0, 1)
    if image.shape[0] != 3:
        raise ValueError("expected RGB image")
    if float(image.max()) > 1.5:
        image = image / 255.0
    return F.interpolate(
        image.unsqueeze(0),
        size=image_size,
        mode="bilinear",
        align_corners=False,
    ).squeeze(0)


def normalize_wheels(wheels: torch.Tensor, stats: DrivingStats) -> torch.Tensor:
    result = wheels.clone()
    result[..., 1:3] = stats.wheel_rates.normalize(result[..., 1:3])
    return result


class TemporalDrivingDatasetV2(Dataset):
    """Temporal windows that never cross episodes or leak the target action."""

    def __init__(
        self,
        dataset,
        episode_map: dict[int, list[int]],
        episodes: Iterable[int],
        stats: DrivingStats,
        history: int = 6,
        image_size: tuple[int, int] = (224, 384),
        neutral_action=NEUTRAL_ACTION,
    ) -> None:
        if history < 2:
            raise ValueError("history must be >= 2")

        self.dataset = dataset
        self.stats = stats
        self.history = int(history)
        self.image_size = image_size
        self.samples: list[tuple[int, int]] = []
        self.episode_map = episode_map
        self.neutral_action = torch.as_tensor(
            neutral_action, dtype=torch.float32
        )

        if tuple(self.neutral_action.shape) != (2,):
            raise ValueError("neutral_action must have shape [2]")

        for episode in episodes:
            indices = episode_map.get(int(episode))
            if not indices:
                raise ValueError("episode {} not found".format(episode))
            for position in range(len(indices)):
                self.samples.append((int(episode), position))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, item: int) -> dict[str, torch.Tensor]:
        episode, target_position = self.samples[item]
        indices = self.episode_map[episode]

        frame_positions, previous_positions = build_temporal_positions(
            target_position, self.history
        )

        frames = []
        wheels = []
        previous_actions = []

        for frame_position, previous_position in zip(
            frame_positions, previous_positions
        ):
            sample = self.dataset[indices[frame_position]]

            frames.append(prepare_image(sample[IMAGE_KEY], self.image_size))
            wheel = torch.as_tensor(sample[WHEEL_KEY], dtype=torch.float32)
            wheels.append(normalize_wheels(wheel, self.stats))

            if previous_position is None:
                previous = self.neutral_action
            else:
                previous = torch.as_tensor(
                    self.dataset[indices[previous_position]][ACTION_KEY],
                    dtype=torch.float32,
                )

            previous_actions.append(self.stats.action.normalize(previous))

        target_index = indices[target_position]
        target_action = torch.as_tensor(
            self.dataset[target_index][ACTION_KEY], dtype=torch.float32
        )

        return {
            "frames": torch.stack(frames),
            "wheels": torch.stack(wheels),
            "previous_actions": torch.stack(previous_actions),
            "target_action": target_action,
            "target_normalized": self.stats.action.normalize(target_action),
            "episode_index": torch.tensor(episode, dtype=torch.int64),
            "dataset_index": torch.tensor(target_index, dtype=torch.int64),
            "episode_frame_index": torch.tensor(target_position, dtype=torch.int64),
        }
