"""Domain-Native Quantitative Credit & Valuation Engine for Project P01."""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


RATING_TIERS: list[tuple[float, str, int, float]] = [
    (88.0, "AAA", 45, 0.05),
    (80.0, "AA", 75, 0.12),
    (72.0, "A", 115, 0.28),
    (62.0, "BBB", 185, 0.75),
    (50.0, "BB", 320, 2.40),
    (38.0, "B", 490, 6.20),
    (0.0, "CCC", 850, 15.80),
]


class CreditScoreInput(BaseModel):
    issuer_id: str = Field(default="issuer_alpha", min_length=1)
    period: str = Field(default="2025-Q4")
    total_debt: float = Field(default=0.0, ge=0.0)
    shareholders_equity: float = Field(default=100.0)
    current_assets: float = Field(default=100.0, ge=0.0)
    current_liabilities: float = Field(default=100.0, ge=0.0)
    ebit: float = Field(default=0.0)
    interest_expense: float = Field(default=0.0, ge=0.0)
    net_income: float = Field(default=0.0)
    total_assets: Optional[float] = None
    retained_earnings: Optional[float] = None
    revenue: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    market_cap: Optional[float] = None
    prev_roa: Optional[float] = None
    prev_debt_ratio: Optional[float] = None
    prev_current_ratio: Optional[float] = None
    prev_gross_margin: Optional[float] = None
    wacc: float = Field(default=0.09, gt=0.01, lt=0.5)
    terminal_growth: float = Field(default=0.025, ge=-0.02, lt=0.15)


class QuantCreditEngine:
    """Offline deterministic quantitative credit, Z-Score, F-Score, and DCF sensitivity engine."""

    @staticmethod
    def _clamp(val: float, low: float, high: float) -> float:
        return max(low, min(high, val))

    @staticmethod
    def _classify_rating(composite_score: float) -> tuple[str, int, float]:
        for threshold, rating, spread_bps, pd_pct in RATING_TIERS:
            if composite_score >= threshold:
                return rating, spread_bps, pd_pct
        return "CCC", 850, 15.80

    def score_issuer(self, payload: CreditScoreInput | dict[str, Any]) -> dict[str, Any]:
        inp = payload if isinstance(payload, CreditScoreInput) else CreditScoreInput(**payload)

        equity = inp.shareholders_equity
        total_debt = inp.total_debt
        curr_assets = inp.current_assets
        curr_liab = inp.current_liabilities
        ebit = inp.ebit
        interest = inp.interest_expense
        net_income = inp.net_income

        # Derived balance sheet / cash flow items when not explicitly provided
        total_assets = (
            inp.total_assets
            if inp.total_assets is not None and inp.total_assets > 0
            else max(total_debt + max(equity, 1.0), curr_assets, 1.0)
        )
        retained_earnings = (
            inp.retained_earnings
            if inp.retained_earnings is not None
            else net_income * 2.5
        )
        revenue = (
            inp.revenue
            if inp.revenue is not None and inp.revenue > 0
            else max(abs(ebit) * 5.0, total_assets * 0.6, 1.0)
        )
        operating_cash_flow = (
            inp.operating_cash_flow
            if inp.operating_cash_flow is not None
            else net_income * 1.15 + abs(ebit) * 0.10
        )
        market_cap = (
            inp.market_cap
            if inp.market_cap is not None and inp.market_cap > 0
            else max(equity * 1.4, net_income * 12.0, 10.0)
        )

        # Core ratios
        debt_to_equity = round(total_debt / equity, 4) if equity > 0 else 99.0
        current_ratio = round(curr_assets / curr_liab, 4) if curr_liab > 0 else 5.0
        interest_coverage = round(ebit / interest, 4) if interest > 0 else 20.0
        roe = round(net_income / equity, 4) if equity > 0 else -1.0
        roa = round(net_income / total_assets, 4)
        debt_to_assets = round(total_debt / total_assets, 4)
        ebit_margin = round(ebit / revenue, 4) if revenue > 0 else 0.0
        asset_turnover = round(revenue / total_assets, 4)

        # 1. Altman-style Z-Score
        working_capital = curr_assets - curr_liab
        total_liabilities = max(total_debt + curr_liab * 0.5, total_assets - equity, 1.0)
        x1 = working_capital / total_assets
        x2 = retained_earnings / total_assets
        x3 = ebit / total_assets
        x4 = market_cap / total_liabilities
        x5 = revenue / total_assets

        z_score = round(1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5, 4)
        if z_score >= 2.99:
            z_zone = "SAFE"
        elif z_score >= 1.81:
            z_zone = "GREY"
        else:
            z_zone = "DISTRESS"

        # 2. Piotroski-style F-Score (0-9)
        f_criteria = {
            "positive_roa": roa > 0.0,
            "positive_ocf": operating_cash_flow > 0.0,
            "roa_improving": (roa > inp.prev_roa) if inp.prev_roa is not None else (roa > 0.04),
            "accruals_quality": operating_cash_flow > net_income,
            "lower_leverage": (
                (debt_to_assets < inp.prev_debt_ratio)
                if inp.prev_debt_ratio is not None
                else (debt_to_equity < 1.5)
            ),
            "higher_liquidity": (
                (current_ratio > inp.prev_current_ratio)
                if inp.prev_current_ratio is not None
                else (current_ratio >= 1.2)
            ),
            "interest_coverage_adequate": interest_coverage >= 2.5,
            "margin_strength": (
                (ebit_margin > inp.prev_gross_margin)
                if inp.prev_gross_margin is not None
                else (ebit_margin >= 0.10)
            ),
            "asset_turnover_healthy": asset_turnover >= 0.50,
        }
        f_score = sum(1 for passed in f_criteria.values() if passed)

        # 3. Leverage & Liquidity Sub-scores (0-100)
        de_component = self._clamp(100.0 - (debt_to_equity * 24.0), 0.0, 100.0)
        ic_component = self._clamp((interest_coverage / 8.0) * 100.0, 0.0, 100.0)
        leverage_score = round(0.55 * de_component + 0.45 * ic_component, 2)

        cr_component = self._clamp((current_ratio / 2.2) * 100.0, 0.0, 100.0)
        wc_ratio = working_capital / total_assets
        wc_component = self._clamp((wc_ratio + 0.25) / 0.65 * 100.0, 0.0, 100.0)
        liquidity_score = round(0.65 * cr_component + 0.35 * wc_component, 2)

        z_norm = self._clamp((z_score / 4.0) * 100.0, 0.0, 100.0)
        f_norm = (f_score / 9.0) * 100.0

        composite_score = round(
            0.30 * z_norm + 0.25 * f_norm + 0.25 * leverage_score + 0.20 * liquidity_score,
            2,
        )
        rating, spread_bps, pd_1y_pct = self._classify_rating(composite_score)

        # 4. Deterministic DCF & Valuation Sensitivity Summary
        dcf_summary = self._compute_dcf_sensitivity(
            operating_cash_flow=operating_cash_flow,
            ebit=ebit,
            roe=roe,
            total_debt=total_debt,
            cash_proxy=curr_assets * 0.25,
            wacc=inp.wacc,
            terminal_growth=inp.terminal_growth,
        )

        return {
            "issuer_id": inp.issuer_id,
            "period": inp.period,
            "credit_rating": rating,
            "composite_score": composite_score,
            "implied_spread_bps": spread_bps,
            "probability_of_default_1y_pct": pd_1y_pct,
            "altman_z_score": {
                "score": z_score,
                "zone": z_zone,
                "components": {
                    "x1_working_capital_to_assets": round(x1, 4),
                    "x2_retained_earnings_to_assets": round(x2, 4),
                    "x3_ebit_to_assets": round(x3, 4),
                    "x4_mcap_to_liabilities": round(x4, 4),
                    "x5_revenue_to_assets": round(x5, 4),
                },
            },
            "piotroski_f_score": {
                "score": f_score,
                "max_score": 9,
                "criteria": f_criteria,
            },
            "sub_scores": {
                "leverage_score": leverage_score,
                "liquidity_score": liquidity_score,
            },
            "ratios": {
                "debt_to_equity": debt_to_equity,
                "current_ratio": current_ratio,
                "interest_coverage": interest_coverage,
                "roe": roe,
                "roa": roa,
                "ebit_margin": ebit_margin,
                "asset_turnover": asset_turnover,
            },
            "dcf_valuation": dcf_summary,
        }

    def _compute_dcf_sensitivity(
        self,
        operating_cash_flow: float,
        ebit: float,
        roe: float,
        total_debt: float,
        cash_proxy: float,
        wacc: float,
        terminal_growth: float,
    ) -> dict[str, Any]:
        fcf_base = max(operating_cash_flow - abs(ebit) * 0.15, operating_cash_flow * 0.7, 1.0)
        proj_growth = self._clamp(roe * 0.35 if roe > 0 else 0.02, 0.02, 0.12)

        def _dcf_ev(rate: float, tg: float) -> tuple[float, float]:
            eff_rate = max(rate, tg + 0.015)
            pv_fcf = 0.0
            fcf_t = fcf_base
            for year in range(1, 6):
                fcf_t = fcf_t * (1.0 + proj_growth)
                pv_fcf += fcf_t / ((1.0 + eff_rate) ** year)
            terminal_val = (fcf_t * (1.0 + tg)) / (eff_rate - tg)
            pv_tv = terminal_val / ((1.0 + eff_rate) ** 5)
            ev = round(pv_fcf + pv_tv, 2)
            eq_val = round(ev - total_debt + cash_proxy, 2)
            return ev, eq_val

        base_ev, base_eq = _dcf_ev(wacc, terminal_growth)
        wacc_steps = [round(max(0.03, wacc - 0.01), 4), round(wacc, 4), round(wacc + 0.01, 4)]
        tg_steps = [
            round(max(0.0, terminal_growth - 0.005), 4),
            round(terminal_growth, 4),
            round(terminal_growth + 0.005, 4),
        ]

        sensitivity_matrix: list[dict[str, Any]] = []
        for r in wacc_steps:
            row_vals: dict[str, float] = {}
            for g in tg_steps:
                _, eq_v = _dcf_ev(r, g)
                row_vals[f"{g * 100:.2f}%"] = eq_v
            sensitivity_matrix.append(
                {
                    "wacc": f"{r * 100:.2f}%",
                    "equity_values_by_terminal_growth": row_vals,
                }
            )

        return {
            "fcf_base": round(fcf_base, 2),
            "projected_5y_growth": round(proj_growth, 4),
            "wacc": round(wacc, 4),
            "terminal_growth": round(terminal_growth, 4),
            "enterprise_value": base_ev,
            "implied_equity_value": base_eq,
            "sensitivity_matrix": sensitivity_matrix,
        }
