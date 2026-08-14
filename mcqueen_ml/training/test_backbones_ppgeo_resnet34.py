"""Smoke tests for PPGeo ResNet-34 visual backbone adapter.

Requires the real PPGeo checkpoint (MCQUEEN_PPGEO_CKPT or the default
~/Downloads/mcqueen_ppgeo/ppgeo_visual_encoder.pth). The default unittest
discovery in CI-less environments may skip if the file is absent; each test
here SKIPS (not fails) when the checkpoint is missing, so the suite stays
green on machines without weights.
"""

import os
import unittest

import torch

from mcqueen_ml.training.backbones import PPGeoResNet34Backbone

DEFAULT_CKPT = os.path.join(
    os.path.expanduser("~"), "Downloads", "mcqueen_ppgeo", "ppgeo_visual_encoder.pth"
)


def _ckpt_path():
    return os.environ.get("MCQUEEN_PPGEO_CKPT", DEFAULT_CKPT)


class PPGeoResNet34BackboneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ckpt = _ckpt_path()
        if not os.path.isfile(cls.ckpt):
            raise unittest.SkipTest("PPGeo checkpoint not present: %s" % cls.ckpt)

    def test_missing_checkpoint_raises_without_fallback(self):
        with self.assertRaises(RuntimeError):
            PPGeoResNet34Backbone(weights_path="/nonexistent/ppgeo.pth")

    def test_builds_and_matches_contract(self):
        backbone = PPGeoResNet34Backbone(weights_path=self.ckpt)
        self.assertEqual(backbone.output_dim, 512)
        self.assertIsInstance(backbone.net.fc, torch.nn.Identity)

    def test_forward_shape_and_variability(self):
        backbone = PPGeoResNet34Backbone(weights_path=self.ckpt)
        backbone.eval()
        with torch.no_grad():
            frames = torch.rand(6, 3, 224, 224)
            feats = backbone(frames)
        self.assertEqual(feats.shape, (6, 512))
        self.assertFalse(torch.allclose(feats, feats[0:1].expand_as(feats)))

    def test_weights_actually_loaded(self):
        backbone = PPGeoResNet34Backbone(weights_path=self.ckpt)
        sd = torch.load(self.ckpt, map_location="cpu")["state_dict"]
        self.assertTrue(
            torch.equal(
                backbone.net.conv1.weight.data,
                sd["conv1.weight"],
            )
        )
        self.assertTrue(
            torch.equal(
                backbone.net.layer4[0].bn1.weight.data,
                sd["layer4.0.bn1.weight"],
            )
        )

    def test_strict_torchvision_compatibility(self):
        import torchvision.models as tvm

        sd = torch.load(self.ckpt, map_location="cpu")["state_dict"]
        net = tvm.resnet34(weights=None)
        net.load_state_dict(sd, strict=True)
        net.fc = torch.nn.Identity()
        net.eval()
        backbone = PPGeoResNet34Backbone(weights_path=self.ckpt)
        backbone.eval()
        with torch.no_grad():
            frames = torch.rand(2, 3, 224, 224)
            x = (frames - backbone._mean) / backbone._std
            self.assertTrue(torch.equal(backbone(frames), net(x)))


if __name__ == "__main__":
    unittest.main()