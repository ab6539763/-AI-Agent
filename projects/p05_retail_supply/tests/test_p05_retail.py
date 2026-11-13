"""Pytest suite for Project P05: Retail & Supply Chain Growth Agent."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure projects/p05_retail_supply is importable regardless of pytest rootdir
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api import create_app  # noqa: E402
from app.fde_pipeline import RetailFDEPipeline  # noqa: E402
from app.llm_wiki import RetailLLMWiki  # noqa: E402
from app.ontology import (  # noqa: E402
    ActionStatus,
    DemandForecast,
    RetailOntologyRegistry,
    SKU,
    Supplier,
    Warehouse,
)


def test_ontology_safety_stock_and_lead_time_checks() -> None:
    registry = RetailOntologyRegistry()
    registry.register_warehouse(
        Warehouse(warehouse_id="WH-1", name="Main Hub", region="US-EAST", capacity_units=10000)
    )
    registry.register_supplier(
        Supplier(supplier_id="SUP-1", name="Acme Supply", lead_time_days=10, moq=50)
    )
    registry.register_sku(
        SKU(
            sku_id="SKU-CRIT",
            name="Critical Widget",
            category="Electronics",
            unit_cost=20.0,
            list_price=50.0,
            current_stock=30,
            safety_stock=50,
            reorder_point=80,
            warehouse_id="WH-1",
            supplier_id="SUP-1",
        )
    )
    registry.register_forecast(
        DemandForecast(
            forecast_id="FC-1",
            sku_id="SKU-CRIT",
            horizon_days=14,
            daily_demand_avg=10.0,
            seasonality_factor=1.0,
        )
    )

    result = registry.check_safety_stock("SKU-CRIT")
    assert result.risk_level == "CRITICAL"
    assert result.below_safety_stock is True
    assert result.lead_time_breach is True
    assert result.days_of_supply == 3.0
    assert result.recommended_order_qty >= 50
    assert len(registry.get_neighbors("SKU-CRIT")) == 3


def test_llm_wiki_ingest_query_and_persistence(tmp_path: Path) -> None:
    wiki = RetailLLMWiki(wiki_dir=tmp_path / "wiki")

    res = wiki.ingest(
        doc_id="DOC-01",
        title="Espresso Maker SOP",
        content="Restock [[SKU-1001]] from [[SUP-01]] into [[WH-EAST]] before Q4 peak.",
        entity_id="SKU-1001",
        entity_type="SKU",
    )
    assert res["entity_id"] == "SKU-1001"
    assert set(res["extracted_links"]) == {"SUP-01", "WH-EAST"}
    assert (tmp_path / "wiki" / "index.md").exists()
    assert (tmp_path / "wiki" / "log.md").exists()
    assert (tmp_path / "wiki" / "entities" / "SKU-1001.md").exists()

    q = wiki.query("Espresso Maker SUP-01")
    assert len(q["matches"]) == 1
    assert q["matches"][0]["entity_id"] == "SKU-1001"
    assert "[[SKU-1001]]" in q["answer"]


def test_llm_wiki_lint_detects_stockout_promo_conflict_and_orphans(tmp_path: Path) -> None:
    wiki = RetailLLMWiki(wiki_dir=tmp_path / "wiki")

    # 1. Orphan SKU with no links + stockout keyword + conflicting promo rules
    wiki.ingest(
        doc_id="DOC-ORPHAN",
        title="Orphan Promo SKU",
        content=(
            "SKU-9999 is below safety stockout threshold. "
            "Promo A gives 15% off stackable, Promo B gives 35% off non-stackable."
        ),
        entity_id="SKU-9999",
        entity_type="SKU",
    )

    report = wiki.lint()
    assert report["status"] == "ISSUES_FOUND"
    assert any(r["sku_id"] == "SKU-9999" for r in report["stockout_risks"])
    assert any(c["entity_id"] == "SKU-9999" for c in report["conflicting_promo_rules"])
    assert any(o["sku_id"] == "SKU-9999" for o in report["orphan_skus"])


def test_fde_pipeline_margin_guardrail_blocks_low_margin_price(tmp_path: Path) -> None:
    registry = RetailOntologyRegistry()
    registry.seed_demo_data()
    wiki = RetailLLMWiki(wiki_dir=tmp_path / "wiki")
    pipeline = RetailFDEPipeline(ontology=registry, wiki=wiki)
    pipeline.seed_wiki_from_ontology()

    # SKU-1001 has unit_cost=120.0, min_margin_pct=0.20 -> price 130.0 gives ~7.7% margin (violates floor)
    result = pipeline.plan_replenishment(
        sku_id="SKU-1001",
        requested_qty=0,
        proposed_price=130.0,
        actor="pricing-bot",
    )
    assert result["action"]["status"] == ActionStatus.BLOCKED.value
    assert result["margin_guardrail"]["passed"] is False
    assert len(pipeline.audit_trail) == 1
    assert pipeline.audit_trail[0]["event"] == "MARGIN_GUARDRAIL_BLOCKED"


def test_fde_pipeline_hitl_gate_and_merchandiser_approval(tmp_path: Path) -> None:
    registry = RetailOntologyRegistry()
    registry.seed_demo_data()
    wiki = RetailLLMWiki(wiki_dir=tmp_path / "wiki")
    pipeline = RetailFDEPipeline(ontology=registry, wiki=wiki)
    pipeline.seed_wiki_from_ontology()

    initial_stock = registry.skus["SKU-1001"].current_stock
    # Bulk PO (qty=250 >= 200 and cost=30000 >= 5000) -> must trigger HITL
    plan = pipeline.plan_replenishment(sku_id="SKU-1001", requested_qty=250)
    action_id = plan["action"]["action_id"]
    assert plan["action"]["requires_hitl"] is True
    assert plan["action"]["status"] == ActionStatus.PENDING_APPROVAL.value
    assert registry.skus["SKU-1001"].current_stock == initial_stock

    # Merchandiser approves
    approval = pipeline.approve_action(
        action_id=action_id,
        approved=True,
        approver="merchandiser-lead",
        comment="Approved for Q4 surge",
    )
    assert approval["action"]["status"] == ActionStatus.EXECUTED.value
    assert approval["sku_stock_after"] == initial_stock + 250


def test_fastapi_endpoints_and_request_id_middleware(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path / "app_data")
    client = TestClient(app)

    health = client.get("/health", headers={"X-Request-ID": "req-test-123"})
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.headers["X-Request-ID"] == "req-test-123"

    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["skus_loaded"] == 3

    inv = client.get("/api/v1/ontology/inventory")
    assert inv.status_code == 200
    assert inv.json()["total"] == 3

    ingest = client.post(
        "/api/v1/wiki/ingest",
        json={
            "doc_id": "API-DOC-1",
            "title": "Flash Sale Rule",
            "content": "Apply 10% off on [[SKU-1002]] with [[WH-WEST]] fulfillment.",
            "entity_id": "SKU-1002",
            "entity_type": "SKU",
        },
    )
    assert ingest.status_code == 200
    assert ingest.json()["entity_id"] == "SKU-1002"

    lint = client.get("/api/v1/wiki/lint")
    assert lint.status_code == 200
    assert "stockout_risks" in lint.json()

    # Replenish SKU-1001 (triggers HITL because recommended qty/cost exceeds threshold)
    repl = client.post("/api/v1/supply/replenish", json={"sku_id": "SKU-1001"})
    assert repl.status_code == 200
    action = repl.json()["action"]
    assert action["status"] == "PENDING_APPROVAL"

    approve = client.post(
        "/api/v1/actions/approve",
        json={
            "action_id": action["action_id"],
            "approved": True,
            "approver": "alice-merchandiser",
            "comment": "LGTM",
        },
    )
    assert approve.status_code == 200
    assert approve.json()["action"]["status"] == "EXECUTED"

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["requests_total"] >= 7
    assert metrics.json()["actions_total"] >= 1


def test_cors_middleware_allows_cross_origin_requests(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path / "cors_data")
    client = TestClient(app)

    preflight = client.options(
        "/api/v1/dashboard/overview",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers.get("access-control-allow-origin") == "*"

    resp = client.get(
        "/api/v1/dashboard/overview",
        headers={"Origin": "http://localhost:5173"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "*"


def test_enterprise_dashboard_wiki_actions_and_audit_endpoints(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path / "enterprise_data")
    client = TestClient(app)

    overview = client.get("/api/v1/dashboard/overview")
    assert overview.status_code == 200
    ov = overview.json()
    assert ov["total_skus"] == 3
    assert ov["suppliers"] == 2
    assert ov["warehouses"] == 2
    assert ov["wiki_pages"] == 7  # 2 warehouses + 2 suppliers + 3 SKUs
    assert ov["stockout_alerts"] >= 2
    assert ov["pending_hitl_pos"] == 0

    pages = client.get("/api/v1/wiki/pages")
    assert pages.status_code == 200
    pages_data = pages.json()
    assert pages_data["total"] == 7
    sample_page = pages_data["items"][0]
    assert {"id", "title", "path", "preview"}.issubset(sample_page.keys())

    query_res = client.get("/api/v1/wiki/query", params={"q": "Espresso"})
    assert query_res.status_code == 200
    assert len(query_res.json()["matches"]) >= 1

    # Trigger a bulk replenishment that requires HITL
    repl = client.post("/api/v1/supply/replenish", json={"sku_id": "SKU-1001", "requested_qty": 220})
    assert repl.status_code == 200
    action_id = repl.json()["action"]["action_id"]

    pending = client.get("/api/v1/actions/pending")
    assert pending.status_code == 200
    assert pending.json()["total"] == 1
    assert pending.json()["items"][0]["action_id"] == action_id

    # Overview reflects pending HITL PO and audit log
    ov_after = client.get("/api/v1/dashboard/overview").json()
    assert ov_after["pending_hitl_pos"] == 1
    assert ov_after["audit_logs"] >= 1

    logs = client.get("/api/v1/audit/logs")
    assert logs.status_code == 200
    assert logs.json()["total"] >= 1
    assert logs.json()["items"][0]["event"] == "REPLENISHMENT_PLANNED"


def test_enterprise_margin_simulation_endpoint_and_guardrail(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path / "sim_data")
    client = TestClient(app)

    # Multi-SKU simulation: SKU-1001 with 15% off passes (>=20% floor),
    # SKU-1002 with 60% off breaches 25% margin floor -> blocked
    sim = client.post(
        "/api/v1/supply/margin-simulate",
        json={
            "items": [
                {"sku_id": "SKU-1001", "promo_discount_pct": 0.15, "projected_units": 100},
                {"sku_id": "SKU-1002", "promo_discount_pct": 0.60, "projected_units": 200},
            ]
        },
    )
    assert sim.status_code == 200
    data = sim.json()
    assert data["total_skus_simulated"] == 2
    assert data["guardrail_passed_count"] == 1
    assert data["guardrail_blocked_count"] == 1
    assert data["all_passed"] is False
    assert data["results"][0]["guardrail_passed"] is True
    assert data["results"][1]["guardrail_passed"] is False

    # Unknown SKU returns 404
    bad_sim = client.post(
        "/api/v1/supply/margin-simulate",
        json={"items": [{"sku_id": "SKU-UNKNOWN", "promo_discount_pct": 0.1}]},
    )
    assert bad_sim.status_code == 404

