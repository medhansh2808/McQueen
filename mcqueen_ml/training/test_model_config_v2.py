import unittest

from mcqueen_ml.training.model_config_v2 import (
    DEFAULT_POLICY_CONFIG,
    TemporalPolicyConfig,
)


class TemporalPolicyConfigTests(unittest.TestCase):
    def test_default_config(self):
        DEFAULT_POLICY_CONFIG.validate()
        self.assertEqual(DEFAULT_POLICY_CONFIG.backbone, "ppgeo_resnet34")
        self.assertEqual(DEFAULT_POLICY_CONFIG.history, 6)
        self.assertEqual(DEFAULT_POLICY_CONFIG.model_dim, 512)
        self.assertEqual(DEFAULT_POLICY_CONFIG.attention_heads, 8)

    def test_drive_jepa_is_supported(self):
        TemporalPolicyConfig(backbone="drive_jepa_vit").validate()

    def test_rejects_single_frame(self):
        with self.assertRaises(ValueError):
            TemporalPolicyConfig(history=1).validate()

    def test_rejects_bad_attention_shape(self):
        with self.assertRaises(ValueError):
            TemporalPolicyConfig(model_dim=510, attention_heads=8).validate()


if __name__ == "__main__":
    unittest.main()
