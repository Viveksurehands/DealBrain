"""
Automated Test Suite for Hindsight Engine (Phase 1)
Validates read path contract, ambiguity resolution, zero-hallucination guarantees,
and structured interaction writes.
"""

import unittest
import tempfile
import os
import shutil
from pathlib import Path
from hindsight.engine import HindsightEngine

class TestHindsightEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.store_file = Path(self.test_dir) / "test_hindsight_store.json"
        self.engine = HindsightEngine(store_path=str(self.store_file))

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_missing_account_returns_exact_contract_string(self):
        result = self.engine.lookup_account("non_existent_account_123")
        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["message"], "No prior history found for this account in Hindsight")

    def test_account_creation_and_exact_id_lookup(self):
        self.engine.upsert_account(
            account_id="acc_acme_001",
            company_name="Acme Corp",
            industry="Enterprise SaaS",
            arr_estimate=120000.0,
            current_stage="Discovery"
        )
        result = self.engine.lookup_account("acc_acme_001")
        self.assertEqual(result["status"], "found")
        self.assertEqual(result["match_type"], "exact_id")
        self.assertEqual(result["account"]["company_name"], "Acme Corp")

    def test_ambiguous_account_lookup_returns_candidates(self):
        # Create two accounts with similar names
        self.engine.upsert_account(account_id="acc_apex_us", company_name="Apex Global US")
        self.engine.upsert_account(account_id="acc_apex_eu", company_name="Apex Global EU")

        result = self.engine.lookup_account("Apex Global")
        self.assertEqual(result["status"], "ambiguous")
        self.assertIn("Multiple records found", result["message"])
        self.assertEqual(len(result["candidates"]), 2)

    def test_interaction_logging_and_single_line_confirmation(self):
        self.engine.upsert_account(
            account_id="acc_fintech_99",
            company_name="Fintech Pro",
            current_stage="Technical Evaluation"
        )

        log_result = self.engine.log_interaction(
            account_id="acc_fintech_99",
            interaction_date="2026-09-20",
            interaction_type="call",
            stakeholders_present=[
                {"name": "Sarah Chen", "role": "VP Engineering", "sentiment": "skeptical", "sentiment_note": "concerned about latency"}
            ],
            objections_raised=[
                {"category": "technical", "objection_text": "Sub-50ms latency SLA requirement", "handling_attempted": "Offered dedicated VPC routing", "resolved": False},
                {"category": "pricing", "objection_text": "Setup fee is outside current quarter budget", "resolved": False}
            ],
            competitors_mentioned=[
                {"name": "DataFast Inc", "context": "Evaluating their real-time streaming tier", "comparative_angle_used": "Enterprise security and HIPAA compliance"}
            ],
            commitments_made=[
                {"owner": "rep", "description": "Send architecture whitepaper and latency benchmarks", "due_date": "2026-09-22"},
                {"owner": "prospect", "description": "Provide network topology diagram", "due_date": "2026-09-24"}
            ],
            deal_stage_signal="Technical Evaluation",
            summary="Technical deep dive with VP Eng regarding throughput and latency SLAs."
        )

        self.assertEqual(log_result["status"], "success")
        self.assertEqual(
            log_result["confirmation_message"],
            "Logged: 2 new objections, 1 competitor mention, 2 open action items."
        )

        # Verify Hindsight state
        acc = self.engine.get_account("acc_fintech_99")
        self.assertEqual(len(acc["objections"]), 2)
        self.assertEqual(len(acc["competitors"]), 1)
        self.assertEqual(len(acc["commitments"]), 2)
        self.assertEqual(len(acc["interaction_history"]), 1)

    def test_stakeholder_sentiment_delta_tracking(self):
        self.engine.upsert_account(account_id="acc_delta_01", company_name="Delta Cloud")

        # First interaction - positive sentiment
        self.engine.log_interaction(
            account_id="acc_delta_01",
            interaction_date="2026-09-03",
            interaction_type="call",
            stakeholders_present=[
                {"name": "Mark Evans", "role": "Head of Finance", "sentiment": "flexible", "sentiment_note": "open to multi-year pilot"}
            ]
        )

        # Second interaction - sentiment shifts to skeptical
        self.engine.log_interaction(
            account_id="acc_delta_01",
            interaction_date="2026-09-20",
            interaction_type="meeting",
            stakeholders_present=[
                {"name": "Mark Evans", "role": "Head of Finance", "sentiment": "fixed at $80K", "sentiment_note": "new CFO mandate"}
            ]
        )

        shifts = self.engine.get_stakeholders_sentiment_delta("acc_delta_01")
        self.assertEqual(len(shifts), 1)
        shift = shifts[0]
        self.assertEqual(shift["name"], "Mark Evans")
        self.assertIn("Shifted from 'flexible' on 2026-09-03 to 'fixed at $80K' on 2026-09-20", shift["notable_change"])

    def test_cross_deal_pattern_retrospective(self):
        # Deal 1 - Won with competitor DataDog and pricing objection
        self.engine.upsert_account(account_id="d1", company_name="Deal One", status="won")
        self.engine.log_interaction(
            account_id="d1",
            interaction_date="2026-08-01",
            interaction_type="call",
            objections_raised=[{"category": "pricing", "objection_text": "Price too high", "handling_attempted": "2-year commitment discount", "resolved": True}]
        )

        # Deal 2 - Lost with pricing objection
        self.engine.upsert_account(account_id="d2", company_name="Deal Two", status="lost")
        self.engine.log_interaction(
            account_id="d2",
            interaction_date="2026-08-10",
            interaction_type="call",
            objections_raised=[{"category": "pricing", "objection_text": "Above budget", "handling_attempted": "Offered feature reduction", "resolved": False}]
        )

        pattern = self.engine.query_cross_deal_patterns(category="pricing")
        self.assertEqual(pattern["sample_size"], 2)
        self.assertEqual(pattern["won_count"], 1)
        self.assertEqual(pattern["lost_count"], 1)
        self.assertEqual(pattern["win_rate_percentage"], 50.0)
        self.assertIn("2-year commitment discount", pattern["effective_tactics"])

if __name__ == "__main__":
    unittest.main()
