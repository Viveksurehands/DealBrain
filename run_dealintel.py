"""
DealIntel Execution Runner
Run interactive enterprise deal intelligence session or automated live simulation.
"""

import sys
import argparse

# Ensure utf-8 stdout for Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from hindsight.agent import DealIntelAgent

def run_simulation(agent: DealIntelAgent):
    print("\n" + "=" * 80)
    print("DEALINTEL - LIVE DEMO & VALIDATION RUN")
    print("Zero-Hallucination Enterprise Deal Intelligence Co-Pilot")
    print("=" * 80 + "\n")

    scenarios = [
        (
            "SCENARIO 1: Rep asks for a brief on a deal with NO prior history in Hindsight",
            "I have an upcoming call with GlobalCorp tomorrow morning. Can you brief me?"
        ),
        (
            "SCENARIO 2: Rep logs a new deal call with objections, competitor, and commitments",
            """Just got off a call with Acme Corp (John Smith, VP Engineering, and Sarah Chen, CFO). 
John is engaged and asking about our VPC architecture, but Sarah pushed back hard saying: 'Your pricing is 15% above Datadog and setup fee is outside this quarter budget.'
I countered by explaining our end-to-end analytics and proposed phased implementation.
Action items: Rep to send custom ROI model and customer references by Friday; John to share security questionnaire by next Monday.
Deal stage moving to Technical Evaluation."""
        ),
        (
            "SCENARIO 3: Rep asks for a pre-call briefing before meeting Acme again",
            "Brief me before my call with Acme Corp tomorrow."
        ),
        (
            "SCENARIO 4: Rep asks how to handle a specific pricing pushback",
            "Sarah at Acme is still questioning the 15% premium over Datadog. How do I respond in my email?"
        )
    ]

    for title, prompt in scenarios:
        print("-" * 80)
        print(f">> {title}")
        print(f"REP: \"{prompt.strip()}\"\n")
        print("DEALINTEL:")
        response = agent.process_message(prompt)
        print(response)
        print("-" * 80 + "\n")

def run_interactive(agent: DealIntelAgent):
    print("\n" + "=" * 80)
    print("DEALINTEL - ENTERPRISE SALES CO-PILOT (Interactive Session)")
    print("Connected to Hindsight Cloud & Groq Inference Engine")
    print("Type 'exit' or 'quit' to end session.")
    print("=" * 80 + "\n")

    while True:
        try:
            user_input = input("REP > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q"]:
                print("\nDealIntel signed off.")
                break
            print("\nDEALINTEL:")
            response = agent.process_message(user_input)
            print(response + "\n")
        except (KeyboardInterrupt, EOFError):
            print("\nDealIntel signed off.")
            break

def main():
    parser = argparse.ArgumentParser(description="DealIntel Enterprise Sales AI Co-Pilot")
    parser.add_argument("--demo", action="store_true", help="Run automated demonstration scenarios")
    args = parser.parse_args()

    agent = DealIntelAgent()

    if args.demo:
        run_simulation(agent)
    else:
        # If in non-interactive environment or asked to run, execute the validation demo
        if not sys.stdin.isatty():
            run_simulation(agent)
        else:
            run_interactive(agent)

if __name__ == "__main__":
    main()
