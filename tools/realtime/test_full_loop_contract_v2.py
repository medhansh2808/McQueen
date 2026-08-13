import unittest

from tools.realtime.full_loop_contract_v2 import FrameLedger


class FullLoopContractTests(unittest.TestCase):
    def test_exact_frame_match(self):
        ledger = FrameLedger()
        ledger.register_capture(7, 1_000_000_000)
        ledger.mark_metadata(7)
        ledger.mark_video(7)
        ledger.mark_inference(7, 7, 2.0)
        ledger.mark_control_sent(7)
        ledger.mark_control_ack(7, 1_070_000_000)

        done = ledger.completed()
        self.assertEqual(len(done), 1)
        self.assertAlmostEqual(done[0].latency_ms(), 70.0)

    def test_mismatched_frame_is_not_complete(self):
        ledger = FrameLedger()
        ledger.register_capture(7, 1_000_000_000)
        ledger.mark_metadata(7)
        ledger.mark_video(7)
        ledger.mark_inference(7, 6, 2.0)
        ledger.mark_control_sent(7)
        ledger.mark_control_ack(7, 1_070_000_000)
        self.assertEqual(ledger.completed(), [])


if __name__ == "__main__":
    unittest.main()
