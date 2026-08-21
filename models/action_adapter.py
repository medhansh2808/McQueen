import cv2
import numpy as np
import torch
import torch.nn as nn

from onnx2pytorch import ConvertModel
import onnx


def rgb_to_supercombo_yuv(frame_rgb: np.ndarray) -> np.ndarray:
    assert frame_rgb.shape[:2] == (256, 512), f"expected (256,512,3), got {frame_rgb.shape}"

    yuv = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2YUV_I420)  # (384, 512)
    H, W = 256, 512
    y = yuv[:H, :]                                   # (256, 512)
    u = yuv[H:H + H // 4, :].reshape(H // 2, W // 2)   # (128, 256)
    v = yuv[H + H // 4:H + H // 2, :].reshape(H // 2, W // 2)  # (128, 256)

    y0 = y[0::2, 0::2]
    y1 = y[0::2, 1::2]
    y2 = y[1::2, 0::2]
    y3 = y[1::2, 1::2]

    packed = np.stack([y0, y1, y2, y3, u, v], axis=0)  # (6, 128, 256)
    return packed.astype(np.uint8)   # raw pixel bytes — the graph normalizes internally via its own _mean/_std


class FrozenActionModel(nn.Module):
    # Output slice layout of comma's driving_supercombo.onnx (2026 master),
    # VERIFIED 2026-08-17 from the model's own `output_slices` metadata
    # (base64-pickled in model-level metadata_props).
    OUT_SLICES = {
        "meta": slice(0, 55),
        "desire_pred": slice(55, 87),
        "pose": slice(87, 99),
        "wide_from_device_euler": slice(99, 105),
        "road_transform": slice(105, 117),
        "lane_lines": slice(117, 645),
        "lane_lines_prob": slice(645, 653),
        "road_edges": slice(653, 917),
        "lead": slice(917, 1061),
        "lead_prob": slice(1061, 1064),
        "hidden_state": slice(1064, 1576),
        "plan": slice(1576, 2566),
        "desire_state": slice(2566, 2574),
    }
    # comma ModelConstants / drive_helpers (master, VERIFIED 2026-08-17)
    IDX_N = 33
    PLAN_WIDTH = 15
    T_IDXS = [10.0 * ((i / 32.0) ** 2) for i in range(IDX_N)]  # index_function
    MIN_SPEED = 1.0
    MIN_STABLE_DELAY = 0.3

    def __init__(self, onnx_path: str, converted_state_dict_path: str = None):
        """
        Wraps the FULL comma driving_supercombo.onnx (2026 master export:
        img/big_img/features_buffer/desire_pulse/traffic_convention/action_t
        -> single flattened 'outputs' tensor). onnx2pytorch conversion;
        the whole trunk is FROZEN.
        """
        super().__init__()
        onnx_model = onnx.load(onnx_path)
        self.trunk = ConvertModel(onnx_model, experimental=True)

        if converted_state_dict_path is not None:
            self.trunk.load_state_dict(torch.load(converted_state_dict_path))

        for p in self.trunk.parameters():
            p.requires_grad = False
        n_params = sum(p.numel() for p in self.trunk.parameters())
        print(f"frozen trunk: {n_params} params, 0 trainable")

    def forward(self, img, big_img, desire_pulse, traffic_convention, action_t, features_buffer):
        """
        All args match the real onnx input names/shapes (VERIFIED 2026-08-17
        against comma master's driving_supercombo.onnx). desire_pulse /
        traffic_convention / action_t have no McQueen equivalent — pass zeros.

        Returns (action, hidden_state, plan_positions):
          action:         (1, 4) plan-derived [desired_curvature, desired_accel, 0, 0]
                          — convert with action_to_command_torch().
                          Built exactly like comma's get_curvature_from_plan /
                          get_accel_from_plan (master drive_helpers.py).
          hidden_state:   (1, 512) this frame's feature — roll it into next call's
                          features_buffer (shift the 24-step window, append at the end)
          plan_positions: (1, 33, 3) predicted (x, y, z) at 33 future timesteps —
                          parse_mdn means, DIAGNOSTIC ONLY.
        """
        out = self.trunk(
            img=img, big_img=big_img, desire_pulse=desire_pulse,
            traffic_convention=traffic_convention, action_t=action_t,
            features_buffer=features_buffer,
        )
        if isinstance(out, (tuple, list)):
            if len(out) != 1:
                raise RuntimeError(f"expected single flattened output, got {len(out)}")
            out = out[0]
        out = out.view(out.shape[0], -1)
        # 2576 = official export (tail: desire_state 8 + zero pad 2, unused);
        # 2574 = batch-patched export (tools/donkey/patch_onnx_batch.py drops the
        # constant p_pad so the graph is batch-agnostic; slices below unchanged).
        if out.shape[1] not in (2576, 2574):
            raise RuntimeError(
                f"expected flattened output size 2576/2574 (2026 driving_supercombo), "
                f"got {out.shape[1]} — model may have changed; re-read output_slices."
            )

        b = out.shape[0]
        hidden_state = out[:, self.OUT_SLICES["hidden_state"]]                      # (b, 512)
        plan_raw = out[:, self.OUT_SLICES["plan"]]                                  # (b, 990)
        plan = plan_raw.view(b, self.IDX_N, 2 * self.PLAN_WIDTH)                     # (b, 33, 30)
        plan_mu = plan[:, :, :self.PLAN_WIDTH]                                      # parse_mdn means
        plan_positions = plan_mu[:, :, 0:3]                                         # (b, 33, 3)

        # comma get_accel_from_plan / get_curvature_from_plan, vectorized over batch.
        # Note: numpy np.interp is 1-D only, so the small per-sample loop runs only
        # for the plan-derived action (the trained-head training path uses
        # hidden_state and never pays this cost).
        speeds = plan_mu[:, :, 3].cpu().numpy()   # (b, 33)
        accels = plan_mu[:, :, 6].cpu().numpy()
        yaws = plan_mu[:, :, 11].cpu().numpy()
        yaw_rates = plan_mu[:, :, 14].cpu().numpy()
        action_t_sec = 0.05  # DT_MDL (20 Hz)
        v_ego = max(0.0, self.MIN_SPEED)  # McQueen: near-zero speeds -> clamp, comma MIN_SPEED=1.0

        action = torch.zeros(b, 4, dtype=hidden_state.dtype, device=hidden_state.device)
        for k in range(b):
            v_now, a_now = speeds[k, 0], accels[k, 0]
            if action_t_sec < self.MIN_STABLE_DELAY:
                v_target = v_now + (action_t_sec / self.MIN_STABLE_DELAY) * (
                    np.interp(self.MIN_STABLE_DELAY, self.T_IDXS, speeds[k]) - v_now)
            else:
                v_target = np.interp(action_t_sec, self.T_IDXS, speeds[k])
            a_target = 2.0 * (v_target - v_now) / action_t_sec - a_now

            if action_t_sec < self.MIN_STABLE_DELAY:
                psi_target = (action_t_sec / self.MIN_STABLE_DELAY) * np.interp(
                    self.MIN_STABLE_DELAY, self.T_IDXS, yaws[k])
            else:
                psi_target = np.interp(action_t_sec, self.T_IDXS, yaws[k])
            psi_rate = yaw_rates[k, 0]
            curv = 2.0 * psi_target / (v_ego * action_t_sec) - psi_rate / v_ego

            action[k, 0] = curv
            action[k, 1] = a_target
        return action, hidden_state, plan_positions


CAR_LENGTH_M = 0.35           
MAX_STEER_ANGLE_RAD = 0.78     
MAX_SPEED_MPS = 3.0           


def action_to_command(action: torch.Tensor, v_ego: float) -> tuple[float, float]:
    """
    Non-differentiable convenience version — use action_to_command_torch
    instead inside a training loop, or gradients won't flow back to the
    re-initialized action-head layers at all.
    """
    steer_t, throttle_t = action_to_command_torch(action, v_ego)
    return float(steer_t.item()), float(throttle_t.item())


def action_to_command_torch(action: torch.Tensor, v_ego: float) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Torch-native version — keeps the autograd graph intact so training
    actually updates the re-initialized action-head layers. Use this one
    inside train_frozen_action.py, not the float-returning version above.

    action: (1, 4) raw slice from FrozenActionModel.forward().
    v_ego: python float (no gradient needed through speed itself).
    """
    a = action[0]
    denom = max(1.0, v_ego) ** 2
    desired_curvature = a[0] / denom
    desired_accel = a[1]

    steering = torch.atan(CAR_LENGTH_M * desired_curvature) / MAX_STEER_ANGLE_RAD
    steering = torch.clamp(steering, -1.0, 1.0)

    throttle = torch.clamp(desired_accel / MAX_SPEED_MPS, -1.0, 1.0)  # crude accel->throttle scale, needs real calibration

    return steering, throttle
