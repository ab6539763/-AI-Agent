"""CLI Demo & Uvicorn Runner for Project P01: FinTech Research & Compliance Agent."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

import uvicorn

from app.fde_pipeline import FinTechFDEPipeline
from app.llm_wiki import FinTechLLMWiki
from app.ontology import LinkType, OntologyLink, OntologyRegistry


def run_cli_demo() -> None:
    """Run a 100% offline deterministic end-to-end demo without interactive input."""
    with tempfile.TemporaryDirectory(prefix="p01_demo_") as tmp:
        data_dir = Path(tmp)
        wiki = FinTechLLMWiki(data_dir / "wiki")
        ontology = OntologyRegistry()
        pipeline = FinTechFDEPipeline(
            wiki=wiki,
            ontology=ontology,
            audit_log_path=data_dir / "audit_trail.jsonl",
        )

        # 1. Ingest research documents
        pipeline.ingest_document(
            doc_id="doc_2025q4_acme",
            title="Acme FinTech 2025 Q4 Credit Note",
            content="Acme FinTech shows elevated leverage compared to [[issuer_beta]].",
            entities=[
                {
                    "id": "issuer_acme",
                    "name": "Acme FinTech Corp",
                    "type": "Issuer",
                    "ticker": "ACME",
                    "sector": "Consumer Lending",
                    "credit_rating": "BBB",
                    "period": "2025-Q4",
                    "metrics": {"revenue_growth": 0.12},
                    "links": ["issuer_beta"],
                },
                {
                    "id": "issuer_beta",
                    "name": "Beta Payments Ltd",
                    "type": "Issuer",
                    "ticker": "BETA",
                    "sector": "Payments",
                    "credit_rating": "A",
                    "period": "2025-Q4",
                    "metrics": {"revenue_growth": 0.18},
                    "links": ["issuer_acme"],
                },
            ],
        )
        ontology.add_link(
            OntologyLink(
                source_id="issuer_acme",
                target_id="issuer_beta",
                relation=LinkType.PEER_OF,
            )
        )

        # 2. Run research query with financial ratio computation & HITL trigger
        research_res = pipeline.run_research(
            question="Evaluate leverage and liquidity risk for Acme FinTech (contact 13800138000)",
            issuer_id="issuer_acme",
            actor_role="senior_analyst",
            financials={
                "total_debt": 320.0,
                "shareholders_equity": 100.0,
                "current_assets": 85.0,
                "current_liabilities": 110.0,
                "ebit": 18.0,
                "interest_expense": 15.0,
                "net_income": 10.0,
            },
            period="2025-Q4",
        )

        # 3. Approve pending HITL compliance action
        pending = research_res["hitl_pending_action"]
        approval_res = None
        if pending:
            approval_res = pipeline.approve_action(
                action_id=pending["action_id"],
                decision="approve",
                actor_role="compliance_officer",
                approver="alice.chen",
                comment="Verified Q4 debt covenants; freeze limit approved.",
            )

        # 4. Run wiki lint
        lint_res = wiki.lint()

        print("=== P01 FinTech Research & Compliance Demo ===")
        print(json.dumps(
            {
                "question_redacted": research_res["question"],
                "ratios": research_res["ratios"],
                "hitl_action": approval_res["action"] if approval_res else None,
                "wiki_lint_status": lint_res["status"],
                "audit_events_count": len(pipeline.read_audit_trail()),
            },
            indent=2,
            ensure_ascii=False,
        ))


def main() -> None:
    parser = argparse.ArgumentParser(description="P01 FinTech Research & Compliance Agent")
    parser.add_argument(
        "--mode",
        choices=["demo", "serve"],
        default="demo",
        help="Run deterministic CLI demo or start FastAPI uvicorn server.",
    )
    parser.add_argument("--host", default=os.environ.get("P01_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("P01_PORT", "8000")))
    args = parser.parse_args()

    if args.mode == "demo":
        run_cli_demo()
    else:
        uvicorn.run("app.api:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
