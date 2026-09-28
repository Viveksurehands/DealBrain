"""
DealIntel Agent - Enterprise Deal Intelligence Co-Pilot
Orchestrates Hindsight Memory (Cloud & Local) with Groq LLM Inference.
Strictly adheres to the DealIntel System Prompt contract:
- Zero hallucination / no fabricated facts
- Explicit 'No prior history found for this deal in Hindsight' when not found
- Granular structured extraction and single-line confirmations
- Pre-call briefs, objection handling scripts, and win/loss retrospectives
"""

import os
import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

from .engine import HindsightEngine
from .cloud_client import HindsightCloudClient
from .groq_client import GroqClient
from .extractor import DealInteractionExtractor

DEALINTEL_SYSTEM_PROMPT = """You are DealIntel, an AI sales co-pilot for enterprise sales reps and teams.
You act like an elite Sales Operations manager who has perfect recall of every deal interaction, objection pattern, and win/loss signal. Your singular job is to:
1. Eliminate manual CRM digging
2. Surface objection and competitive patterns across the pipeline  
3. Produce actionable, executive-ready briefings that help reps close faster

You are NOT a general-purpose chatbot in this role. Every response must visibly save the rep time versus them reading raw notes or digging through CRM.

MEMORY MODEL (Hindsight):
Hindsight is your persistent memory store. Treat it as the source of truth for deal history. Never invent context or rely on general knowledge for deal-specific facts.

READING FROM MEMORY:
- Before generating a brief, email draft, strategy, or objection response, check Hindsight memory context provided in your prompt.
- If NO records found: Say explicitly "No prior history found for this deal in Hindsight". Do NOT fabricate context or proceed silently as if history exists.
- If ambiguous, ask rep to confirm before proceeding.

WRITING TO MEMORY:
- Extract structured facts without speculative extrapolation.
- Incomplete but accurate record > Complete but speculative record.
- Confirm storage in one line, e.g.: "Logged: 2 new objections, 1 competitor mention, 3 open items"

OUTPUT FORMATS & STYLE:
- Professional, direct, revenue-focused.
- No filler, no motivational language.
- Lead with the answer or recommendation; support it after.
- Use bullet points and short headers over dense prose.
- Reps read this between meetings — be scannable.
"""

class DealIntelAgent:
    def __init__(
        self,
        engine: Optional[HindsightEngine] = None,
        cloud_client: Optional[HindsightCloudClient] = None,
        groq_client: Optional[GroqClient] = None
    ):
        self.engine = engine or HindsightEngine()
        self.cloud_client = cloud_client or HindsightCloudClient()
        self.groq_client = groq_client or GroqClient()
        self.extractor = DealInteractionExtractor(engine=self.engine)

    def process_message(self, user_message: str) -> str:
        """
        Processes incoming rep messages:
        1. Identifies if the rep is sharing a call transcript / new interaction to log
        2. Retrieves memory from Hindsight (local & cloud)
        3. Invokes Groq with system prompt + deal context
        4. Writes new interactions to Hindsight when applicable
        """
        # Step 1: Detect if this is an interaction log request or contains raw meeting notes
        is_interaction = self._is_interaction_content(user_message)
        
        extracted_facts = None
        target_account_id = None
        target_company_name = None

        # Look for existing accounts mentioned in query or message
        account_context_str = ""
        matched_account = None
        
        # Check all known accounts in Hindsight
        all_accounts = self.engine.list_accounts()
        for acc in all_accounts:
            cname = acc.get("company_name", "").lower()
            aid = acc.get("account_id", "").lower()
            if (cname and cname in user_message.lower()) or (aid and aid in user_message.lower()):
                matched_account = acc
                target_account_id = acc["account_id"]
                target_company_name = acc["company_name"]
                break

        # If not found in local engine, check if an account name is explicitly referenced (e.g. "Acme", "TechCorp")
        if not matched_account:
            found_name = self._detect_company_name(user_message)
            if found_name:
                lookup = self.engine.lookup_account(found_name)
                if lookup.get("status") == "found":
                    matched_account = lookup.get("account")
                    target_account_id = matched_account["account_id"]
                    target_company_name = matched_account["company_name"]
                elif lookup.get("status") == "ambiguous":
                    candidates_str = ", ".join([f"{c['company_name']} ({c['account_id']})" for c in lookup.get("candidates", [])])
                    return f"Multiple records found matching '{found_name}': {candidates_str}. Confirm which record before proceeding."
                else:
                    target_company_name = found_name
                    target_account_id = f"acc_{found_name.lower().replace(' ', '_')}"

        # If we have an interaction, extract structured facts
        confirmation_msg = ""
        if is_interaction and target_company_name:
            if not matched_account:
                # Upsert account first
                matched_account = self.engine.upsert_account(
                    account_id=target_account_id,
                    company_name=target_company_name
                )
            
            extracted_facts = self.extractor.extract_from_text(
                raw_text=user_message,
                account_id=target_account_id
            )

            # Log to local Hindsight Engine
            log_res = self.engine.log_interaction(
                account_id=target_account_id,
                interaction_date=extracted_facts.get("interaction_date", datetime.now().strftime("%Y-%m-%d")),
                interaction_type=extracted_facts.get("interaction_type", "call"),
                stakeholders_present=extracted_facts.get("stakeholders_present"),
                objections_raised=extracted_facts.get("objections_raised"),
                competitors_mentioned=extracted_facts.get("competitors_mentioned"),
                commitments_made=extracted_facts.get("commitments_made"),
                deal_stage_signal=extracted_facts.get("deal_stage_signal"),
                summary=extracted_facts.get("summary", ""),
                raw_notes_excerpt=extracted_facts.get("raw_notes_excerpt")
            )
            confirmation_msg = log_res.get("confirmation_message", "Logged: interaction recorded.")

            # Also retain to Hindsight Cloud if available
            try:
                if self.cloud_client.api_key:
                    cloud_summary = f"Interaction with {target_company_name}: {extracted_facts.get('summary', '')}"
                    self.cloud_client.retain(
                        content=f"Deal: {target_company_name} ({target_account_id})\n{user_message}",
                        context=f"sales_deal_{target_account_id}",
                        tags=[target_account_id, "deal_interaction"]
                    )
            except Exception:
                pass  # Local store is primary source of truth

        # Prepare context from Hindsight
        if matched_account:
            sentiment_delta = self.engine.get_stakeholders_sentiment_delta(target_account_id)
            unresolved_obj = self.engine.get_unresolved_objections(target_account_id)
            open_comm = self.engine.get_open_commitments(target_account_id)
            comps = self.engine.get_competitors_in_play(target_account_id)
            patterns = self.engine.query_cross_deal_patterns(category=None)

            account_context_str = f"""
CURRENT HINDSIGHT DEAL RECORD:
Account ID: {matched_account.get('account_id')}
Company Name: {matched_account.get('company_name')}
Stage: {matched_account.get('current_stage')}
Status: {matched_account.get('status')}
Last Activity: {matched_account.get('last_activity_date')}

Stakeholders & Sentiment:
{json.dumps(sentiment_delta, indent=2)}

Unresolved Objections:
{json.dumps(unresolved_obj, indent=2)}

Open Commitments:
{json.dumps(open_comm, indent=2)}

Competitors in Play:
{json.dumps(comps, indent=2)}

Interaction History Count: {len(matched_account.get('interaction_history', []))}
Cross-deal Pattern Basis: {json.dumps(patterns, indent=2)}
"""
        elif any(kw in user_message.lower() for kw in ["brief", "call with", "deal", "prospect", "acme", "history"]):
            account_context_str = "HINDSIGHT RECORD: No prior history found for this deal in Hindsight.\n"

        # Query Hindsight Cloud for semantic memory context if available
        cloud_memories_str = ""
        try:
            if self.cloud_client.api_key:
                recall_res = self.cloud_client.recall(query=user_message, max_tokens=1000)
                mem_items = recall_res.get("results", [])
                if mem_items:
                    cloud_memories_str = "\nHINDSIGHT CLOUD RECALLED MEMORIES:\n" + "\n".join([
                        f"- {m.get('text', '')}" for m in mem_items[:5]
                    ])
        except Exception:
            pass

        # Build prompt for Groq
        user_prompt_with_context = f"""
{account_context_str}
{cloud_memories_str}

REPRESENTATIVE'S MESSAGE:
{user_message}

{"NOTE: This interaction was just extracted and committed to Hindsight memory." if is_interaction else ""}
Follow the DealIntel prompt instructions strictly. Lead with the direct recommendation/answer.
"""

        messages = [
            {"role": "system", "content": DEALINTEL_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt_with_context}
        ]

        response = self.groq_client.chat_completion(messages=messages, temperature=0.1)

        # Append confirmation line if we logged new facts and it wasn't explicitly output
        if confirmation_msg and confirmation_msg.lower() not in response.lower():
            response = f"{response}\n\n{confirmation_msg}"

        return response.strip()

    def _is_interaction_content(self, text: str) -> bool:
        indicators = [
            "just got off a call", "finished call", "spoke with", "had a call",
            "meeting with", "call transcript", "attendees:", "discussed pricing",
            "said pricing is", "pushed back", "objection", "email thread", "from:", "subject:"
        ]
        text_lower = text.lower()
        return any(ind in text_lower for ind in indicators)

    def _detect_company_name(self, text: str) -> Optional[str]:
        # Simple extraction for patterns like "call with [Company]", "at [Company]"
        match = re.search(r"\b(?:with|at|for|about)\s+([A-Z][a-zA-Z0-9_\s]{2,20})\b", text)
        if match:
            cand = match.group(1).split()[0].strip()
            if cand.lower() not in ["the", "our", "their", "him", "her", "them", "a", "an"]:
                return cand
        # Check capitalized known tokens
        for word in text.split():
            clean = re.sub(r"[^\w]", "", word)
            if clean in ["Acme", "TechCorp", "FintechPro", "ApexGlobal", "HealthCorp", "Datadog", "Snowflake"]:
                return clean
        return None
