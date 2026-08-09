"""Tiny McQueen GPU training smoke test.

Purpose: prove that an official LeRobot dataset can be loaded and used for
GPU training. This is NOT the final driving model.
"""

import argparse
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

from lerobot.datasets import LeRobotDataset


class TinyDriver(nn.Module):
    def __init__(self):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 8, kernel_size=5, stride=2, padding=2),
            nn.ReLU(),
            nn.Conv2d(8, 16, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.Conv2d(16, 32, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.head = nn.Linear(32, 2)

    def forward(self, x):
        x = self.features(x)
        x = x.flatten(1)
        return self.head(x)


def load_dataset(root, repo_id):
    dataset = LeRobotDataset(repo_id=repo_id, root=root)

    images = []
    actions = []

    for i in range(len(dataset)):
        frame = dataset[i]

        image = torch.as_tensor(
            frame["observation.images.front_rgb"],
            dtype=torch.float32,
        )

        if float(image.max()) > 1.5:
            image = image / 255.0

        image = F.interpolate(
            image.unsqueeze(0),
            size=(90, 160),
            mode="bilinear",
            align_corners=False,
        ).squeeze(0)

        action = torch.as_tensor(frame["action"], dtype=torch.float32)

        images.append(image)
        actions.append(action)

    return torch.stack(images), torch.stack(actions)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--steps", type=int, default=80)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/mcqueen-tiny-driver.pt"),
    )
    args = parser.parse_args()

    torch.manual_seed(0)

    if not torch.cuda.is_available():
        raise SystemExit("ERROR: CUDA is not available")

    device = torch.device("cuda")

    images, actions = load_dataset(args.root, args.repo_id)

    print("Frames       :", len(images))
    print("Input tensor :", tuple(images.shape))
    print("Action tensor:", tuple(actions.shape))
    print("GPU          :", torch.cuda.get_device_name(0))

    model = TinyDriver().to(device)
    images = images.to(device)
    actions = actions.to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=3e-3)

    model.train()

    initial_loss = None
    final_loss = None

    for step in range(args.steps):
        prediction = model(images)
        loss = F.mse_loss(prediction, actions)

        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        optimizer.step()

        value = float(loss.detach().cpu())

        if initial_loss is None:
            initial_loss = value

        final_loss = value

        if step in {0, 9, 19, 39, args.steps - 1}:
            print("Step {:03d} loss: {:.8f}".format(step + 1, value))

    if final_loss >= initial_loss:
        raise SystemExit(
            "ERROR: training loss did not decrease "
            "({:.8f} -> {:.8f})".format(initial_loss, final_loss)
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)

    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "input_size": [90, 160],
            "action_names": ["steering", "throttle"],
            "initial_loss": initial_loss,
            "final_loss": final_loss,
        },
        args.output,
    )

    print()
    print("Initial loss :", initial_loss)
    print("Final loss   :", final_loss)
    print("Checkpoint   :", args.output)
    print("TINY GPU TRAINING SMOKE TEST : PASS")


if __name__ == "__main__":
    main()
