"""
Automated Test Suite for Extraction & Logging Pipeline (Phase 2)
Validates parsing of call transcripts, email threads, objection detection,
competitor extraction, and deterministic Hindsight write path.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from hindsight.engine import HindsightEngine
from hindsight.extractor import DealInteractionExtractor

SAMPLE_CALL_TRANSCRIPT = """
Call Transcript - 2026-09-22
Attendees: Marcus Vance (VP Infrastructure), Elena Rostova (Director of SecOps)

Marcus Vance (VP Infrastructure): Thanks for jumping on. We are currently evaluating Datadog and Dynatrace for our cloud migration, but latency SLAs are our primary blocker.
Rep: Understandable Marcus. How strict are the latency requirements?
Marcus Vance (VP Infrastructure): Latency concern: We need guaranteed p99 sub-40ms response times across multi-region clusters. Without SLA guarantees, we cannot proceed.
Elena Rostova (Director of SecOps): From our side, SOC2 Type II compliance and HIPAA compliance are mandatory before technical evaluation.
Rep: We have SOC2 Type II and HIPAA certification ready to share.
Elena Rostova (Director of SecOps): Great.

Action Items:
- Rep will send SOC2 report and HIPAA compliance package by 2026-09-24.
- Marcus Vance to provide architecture topology diagram by 2026-09-26.
- Moving to POC pending security review.
"""

SAMPLE_EMAIL_THREAD = """
From: david.ross@enterprise-scale.io
To: rep@dealbrain.ai
Date: 2026-09-25
Subject: Pricing pushback on Enterprise tier proposal

Hi Rep,

We reviewed the initial proposal for $150K ARR. Unfortunately, we have a strict budget concern:
- The annual cost exceeds our Q4 cap of $110K.
- Setup fee of $25K is prohibitive right now.

Can we explore a 2-year commitment discount to bring this into budget?

Best,
David Ross
VP Finance & Operations
"""

class TestInteractionExtractor(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.store_file = Path(self.test_dir) / "test_store.json"
        self.engine = HindsightEngine(store_path=str(self.store_file))
        self.extractor = DealInteractionExtractor(engine=self.engine)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_transcript_extraction(self):
        extracted = self.extractor.extract_from_text(SAMPLE_CALL_TRANSCRIPT)

        self.assertEqual(extracted["interaction_type"], "call")
        self.assertEqual(extracted["interaction_date"], "2026-09-22")

        # Stakeholders
        stk_names = [s["name"] for s in extracted["stakeholders_present"]]
        self.assertIn("Marcus Vance", stk_names)
        self.assertIn("Elena Rostova", stk_names)

        # Competitors
        comp_names = [c["competitor_name"] for c in extracted["competitors_mentioned"]]
        self.assertIn("Datadog", comp_names)
        self.assertIn("Dynatrace", comp_names)

        # Objections
        self.assertGreaterEqual(len(extracted["objections_raised"]), 1)
        categories = [o["category"] for o in extracted["objections_raised"]]
        self.assertTrue("technical" in categories or "security" in categories)

        # Commitments
        self.assertGreaterEqual(len(extracted["commitments_made"]), 2)
        owners = [c["owner"] for c in extracted["commitments_made"]]
        self.assertIn("rep", owners)

        # Stage signal
        self.assertEqual(extracted["deal_stage_signal"], "Technical Evaluation")

    def test_email_pricing_pushback_extraction(self):
        extracted = self.extractor.extract_from_text(SAMPLE_EMAIL_THREAD)

        self.assertEqual(extracted["interaction_type"], "email")
        self.assertEqual(extracted["interaction_date"], "2026-09-25")

        categories = [o["category"] for o in extracted["objections_raised"]]
        self.assertIn("pricing", categories)

    def test_end_to_end_ingest_and_write(self):
        # Create account
        self.engine.upsert_account(
            account_id="acc_titan_77",
            company_name="Titan Cloud Systems",
            current_stage="Discovery"
        )

        result = self.extractor.ingest_and_log(
            raw_text=SAMPLE_CALL_TRANSCRIPT,
            account_id="acc_titan_77"
        )

        self.assertEqual(result["status"], "success")
        self.assertIn("Logged:", result["confirmation_message"])

        # Check account was updated in Hindsight
        acc = self.engine.get_account("acc_titan_77")
        self.assertEqual(acc["current_stage"], "Technical Evaluation")
        self.assertEqual(len(acc["interaction_history"]), 1)
        self.assertGreaterEqual(len(acc["competitors"]), 2)
        self.assertGreaterEqual(len(acc["commitments"]), 2)

if __name__ == "__main__":
    unittest.main()
