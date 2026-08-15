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

 
    ACTION_FINAL_WEIGHT_NAME = "on_policy_model.temporal_hydra.final_layer.action.weight"   # shape [4, 512]
    ACTION_FINAL_BIAS_NAME = "on_policy_model.temporal_hydra.final_layer.action.bias"         # shape [4]
    ACTION_SCALE_NAME = "on_policy_model.temporal_hydra.scale_layer.action.scale"               # shape [4]

    @staticmethod
    def _get_owner_and_attr(root_module: nn.Module, dotted_name: str):
        """
        Resolves 'a.b.c' -> (module_a.module_b, 'c'). Handles the flat,
        no-dot case too (onnx2pytorch registers top-level initializers
        directly on the root module with underscore-joined names, no
        actual submodule nesting) -> (root_module, dotted_name).
        """
        if "." in dotted_name:
            module_path, attr = dotted_name.rsplit(".", 1)
            owner = root_module
            for part in module_path.split("."):
                owner = getattr(owner, part)
            return owner, attr
        return root_module, dotted_name

    def __init__(self, onnx_path: str, converted_state_dict_path: str = None):
        """
        onnx_path should be the EXTRACTED SUBGRAPH from
        extract_action_subgraph.py (mcqueen_action_subgraph.onnx), not the
        full 874-node model — point_policy/off_policy branches were cut,
        they're not needed and just slow down conversion.
        """
        super().__init__()
        onnx_model = onnx.load(onnx_path)
        self.trunk = ConvertModel(onnx_model, experimental=True)

        if converted_state_dict_path is not None:
            self.trunk.load_state_dict(torch.load(converted_state_dict_path))

        # Freeze everything first.
        for p in self.trunk.parameters():
            p.requires_grad = False

        # Find the action-head params by VALUE (not name — onnx2pytorch
        # doesn't reliably preserve onnx initializer names), using the
        # exact arrays from the original onnx file's initializers.
        init_by_name = {init.name: init for init in onnx_model.graph.initializer}
        target_arrays = {}
        for onnx_name in (self.ACTION_FINAL_WEIGHT_NAME, self.ACTION_FINAL_BIAS_NAME, self.ACTION_SCALE_NAME):
            if onnx_name not in init_by_name:
                raise RuntimeError(
                    f"{onnx_name} not found in this onnx file's initializers — "
                    f"did you pass the full model instead of the extracted subgraph, "
                    f"or did comma rename something? Re-run the initializer dump against this file."
                )
            target_arrays[onnx_name] = onnx.numpy_helper.to_array(init_by_name[onnx_name])

        reinitialized = []
        state_dict = self.trunk.state_dict()
        name_map = {}   # onnx_name -> matched torch parameter name
        for onnx_name, onnx_arr in target_arrays.items():
            best_name, best_diff = None, float("inf")
            for torch_name, torch_param in state_dict.items():
                if tuple(torch_param.shape) != tuple(onnx_arr.shape):
                    continue
                d = float((torch_param.numpy().astype("float64") - onnx_arr.astype("float64")).__abs__().max())
                if d < best_diff:
                    best_diff, best_name = d, torch_name
            if best_name is None or best_diff > 1e-2:
                raise RuntimeError(
                    f"Could not confidently match {onnx_name} to a converted PyTorch "
                    f"parameter (best candidate: {best_name}, diff={best_diff}). "
                    f"Print state_dict shapes and compare by hand before proceeding."
                )
            name_map[onnx_name] = best_name

        params_by_name = dict(self.trunk.named_parameters())
        for onnx_name, torch_name in name_map.items():
            owner, attr = self._get_owner_and_attr(self.trunk, torch_name)
            shape = target_arrays[onnx_name].shape

            if torch_name in params_by_name:
                # Rare case: onnx2pytorch already registered it as a real
                # nn.Parameter. Just re-init and unfreeze in place.
                p = params_by_name[torch_name]
                p.requires_grad = True
            else:
                # Expected case: onnx2pytorch registered it as a frozen
                # buffer (constant), since ONNX graphs are inference-only
                # by default. A buffer is invisible to model.parameters(),
                # so setting requires_grad on it wouldn't be enough — it
                # has to be removed from _buffers and re-registered as an
                # actual nn.Parameter for an optimizer to ever touch it.
                if attr in owner._buffers:
                    del owner._buffers[attr]
                elif attr in owner._parameters:
                    del owner._parameters[attr]
                else:
                    raise RuntimeError(
                        f"{torch_name} not found as a parameter or buffer on "
                        f"its owning module — naming assumption broken, print "
                        f"owner._buffers.keys() / owner._parameters.keys() to debug."
                    )
                p = nn.Parameter(torch.empty(shape, dtype=torch.float16), requires_grad=True)
                owner.register_parameter(attr, p)

            if p.dim() > 1:
                nn.init.xavier_uniform_(p.data)
            else:
                nn.init.zeros_(p.data)
            reinitialized.append(torch_name)

        if not reinitialized:
            raise RuntimeError(
                "Matched onnx initializers by value but couldn't re-locate them as "
                "trainable nn.Parameters on the module tree — print name_map and "
                "trunk.state_dict().keys() to debug the mismatch."
            )
        print("re-initialized + unfrozen (dtype=float16, matching the rest of the graph):", reinitialized)

    def forward(self, img, big_img, desire_pulse, traffic_convention, action_t, features_buffer):
        """
        All args match the onnx input shapes. desire_pulse/traffic_convention
        have no McQueen equivalent — pass zeros for them (see train_frozen_action.py).

        Returns (action, hidden_state, plan_positions):
          action:         (1, 4) raw curvature+accel — convert with action_to_command_torch()
          hidden_state:   (1, 512) this frame's feature — roll it into next call's
                          features_buffer (shift the 24-step window, append this at the end)
          plan_positions: (1, 33, 3) predicted (x, y, z) at 33 future timesteps, from the
                          FROZEN off_policy_model branch — DIAGNOSTIC ONLY, not used in
                          training (see module docstring for why it can't be)
        """
        out = self.trunk(
            img=img, big_img=big_img, desire_pulse=desire_pulse,
            traffic_convention=traffic_convention, action_t=action_t,
            features_buffer=features_buffer,
        )
        if not isinstance(out, (tuple, list)) or len(out) != 3:
            raise RuntimeError(
                f"expected 3 outputs (action, hidden_state, plan) from the extracted "
                f"subgraph, got {type(out)} — check extract_action_subgraph.py's "
                f"output_names still matches ['mul_48', 'linear_80', 'mul_41']"
            )
        action, hidden_state, plan_raw = out[0], out[1], out[2]

        # plan_raw: (1, 990) = 33 points x 15 values/point, per your reverse-engineered
        # layout (Plan.POSITION: indices 0:3, VELOCITY: 3:6, ACCELERATION: 6:9,
        # T_FROM_CURRENT_EULER: 9:12, ORIENTATION_RATE: 12:15). Note this is the RAW
        # MDN (mixture density network) output — comma decodes it further with parse_mdn()
        # to get proper means/stds; this is a simplified direct reshape+slice, close
        # enough for logging/sanity-checking but not a fully faithful decode.
        plan = plan_raw.view(1, 33, 15)
        plan_positions = plan[:, :, 0:3]   # (1, 33, 3) — x, y, z per future timestep

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
