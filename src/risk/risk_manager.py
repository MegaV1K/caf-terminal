"""
Unified Institutional Risk Manager for CAF-Terminal.

Serves as the master pre-trade and portfolio risk gateway combining:
- TiltGuard (Anti-Gemini, anti-herding, position & cluster caps)
- DerivativesRiskEngine (Expiration cliff, notional fee drag, liquidity traps, OI pinning)
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from config import REPORTS_DIR
from src.database.registry import CAFRegistry
from src.risk.derivatives_risk import DerivativesRiskEngine
from src.risk.tilt_guard import TiltGuard


class InstitutionalRiskManager:
    """Master risk controller for validating trades, derivatives, and portfolio allocations."""

    def __init__(self):
        self.derivatives = DerivativesRiskEngine()
        self.tilt_guard = TiltGuard()
        self.registry = CAFRegistry()

    def audit_spot_trade(
        self,
        symbol: str,
        requested_weight_pct: float,
        cluster_name: str,
        current_cluster_weight_pct: float,
        drawdown_pct: float = 0.0,
        is_averaging_down: bool = False,
        thesis_source: str = "INDEPENDENT_CVE",
    ) -> Dict[str, Any]:
        """Pre-trade risk evaluation for spot and fundamental allocations."""
        return self.tilt_guard.audit_trade_risk(
            symbol=symbol,
            requested_weight_pct=requested_weight_pct,
            cluster_name=cluster_name,
            current_cluster_weight_pct=current_cluster_weight_pct,
            leverage=1.0,
            asset_drawdown_pct=drawdown_pct,
            is_averaging_down=is_averaging_down,
            thesis_source=thesis_source,
        )

    def audit_derivatives_position(
        self,
        symbol: str,
        contracts: float,
        underlying_price: float,
        option_premium_usd: float,
        expected_profit_usd: float,
        bid_price: float,
        ask_price: float,
        account_equity: float,
        maintenance_margin: float,
        options_collateral_value: float,
        hours_to_expiry: float,
    ) -> Dict[str, Any]:
        """Comprehensive multi-factor risk check for an options or derivatives construction."""
        # 1. Notional fee drag
        fee_check = self.derivatives.calculate_notional_fee_drag(
            symbol=symbol,
            contracts=contracts,
            underlying_price=underlying_price,
            option_premium_usd=option_premium_usd,
            expected_profit_usd=expected_profit_usd,
        )

        # 2. Spread and liquidity trap
        liquidity_check = self.derivatives.validate_liquidity_and_spread(
            symbol=symbol,
            bid_price=bid_price,
            ask_price=ask_price,
            projected_profit_usd=expected_profit_usd,
            contracts=contracts,
        )

        # 3. Expiration margin cliff
        margin_check = self.derivatives.evaluate_expiration_margin_cliff(
            account_equity=account_equity,
            maintenance_margin=maintenance_margin,
            options_collateral_value=options_collateral_value,
            hours_to_expiry=hours_to_expiry,
        )

        is_approved = (
            not fee_check["is_fee_trap"]
            and not margin_check["is_liquidation_hazard"]
            and liquidity_check["status"] != "BLOCKED"
        )

        critical_risks = []
        if fee_check["is_fee_trap"]:
            critical_risks.append(f"FEE_TRAP: {fee_check['fee_drag_pct']}% of profit consumed by fees.")
        if margin_check["is_liquidation_hazard"]:
            critical_risks.append(f"MARGIN_CLIFF: Post-expiry equity (${margin_check['projected_post_expiry_equity']}) below maintenance.")
        if liquidity_check.get("is_liquidity_trap"):
            critical_risks.append(f"LIQUIDITY_TRAP: Wide spread eats {liquidity_check['spread_to_profit_pct']}% of profit.")

        return {
            "symbol": symbol.upper(),
            "is_approved": is_approved,
            "overall_verdict": "APPROVED" if is_approved else "REJECTED_OR_MODIFIED",
            "critical_risks": critical_risks,
            "fee_analysis": fee_check,
            "liquidity_analysis": liquidity_check,
            "margin_cliff_analysis": margin_check,
            "recommended_execution": liquidity_check["execution_mode"],
        }

    def audit_portfolio_risk(self) -> Dict[str, Any]:
        """
        Runs portfolio-wide forensic risk audit:
        - Cluster concentration analysis (max 10% cap).
        - Tilt risk detection on drawdown assets (drawdown > 15%).
        - Broken thesis invalidation alerts (drawdown > 25%).
        - Exports reports/risk_audit_YYYY-MM-DD.md.
        """
        all_assets = self.registry.get_all_assets()
        pnl_data = self.registry.get_pnl_summary()
        pnl_by_sym = {p["symbol"].upper(): p for p in pnl_data}

        # Calculate cluster weights
        cluster_weights: Dict[str, float] = {}
        tilt_risks = []
        invalidation_alerts = []
        cluster_breaches = []

        active_portfolio = [a for a in all_assets if a.get("status") in {"Active", "Portfolio"}]
        total_active = len(active_portfolio) or 1
        equal_weight_proxy = 100.0 / total_active

        for a in active_portfolio:
            sym = a["symbol"].upper()
            sector = a.get("sector") or "Unclassified"
            cluster_weights[sector] = cluster_weights.get(sector, 0.0) + equal_weight_proxy

            pnl_info = pnl_by_sym.get(sym, {})
            pnl_pct = pnl_info.get("pnl_pct") or 0.0

            if pnl_pct <= -25.0:
                invalidation_alerts.append({
                    "symbol": sym,
                    "name": a["name"],
                    "pnl": pnl_pct,
                    "tier": a["tier"],
                    "action": "MANDATORY_THESIS_INVALIDATION_REVIEW",
                })
            elif pnl_pct <= -15.0:
                tilt_risks.append({
                    "symbol": sym,
                    "name": a["name"],
                    "pnl": pnl_pct,
                    "tier": a["tier"],
                    "action": "TILT_LOCK_ACTIVE: Size expansion / leverage increase forbidden",
                })

        for cluster, weight in cluster_weights.items():
            if weight > self.tilt_guard.MAX_CLUSTER_WEIGHT_PCT:
                cluster_breaches.append({
                    "cluster": cluster,
                    "weight_pct": round(weight, 1),
                    "cap_pct": self.tilt_guard.MAX_CLUSTER_WEIGHT_PCT,
                    "excess_pct": round(weight - self.tilt_guard.MAX_CLUSTER_WEIGHT_PCT, 1),
                })

        report_summary = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_active_assets": len(active_portfolio),
            "cluster_breakdown": {k: round(v, 1) for k, v in sorted(cluster_weights.items(), key=lambda x: x[1], reverse=True)},
            "cluster_breaches": cluster_breaches,
            "tilt_locks": tilt_risks,
            "invalidation_alerts": invalidation_alerts,
            "is_healthy": len(cluster_breaches) == 0 and len(invalidation_alerts) == 0,
        }

        report_path = self._save_risk_report(report_summary)
        report_summary["report_path"] = str(report_path)
        return report_summary

    def _save_risk_report(self, summary: Dict[str, Any]) -> Path:
        date_str = datetime.now().strftime("%Y-%m-%d")
        file_path = REPORTS_DIR / f"risk_audit_{date_str}.md"

        lines = [
            f"# Институциональный Аудит Рисков Портфеля — {date_str}\n",
            f"**Дата аудита:** {summary['date']}",
            f"**Статус риска:** {'✅ В ПРЕДЕЛАХ НОРМЫ' if summary['is_healthy'] else '⚠️ ТРЕБУЕТСЯ ВМЕШАТЕЛЬСТВО'}",
            f"**Активных позиций:** {summary['total_active_assets']}\n",
            "## 1. Концентрация по риск-кластерам (Лимит: 10.0% на кластер)\n",
            "| Кластер / Сектор | Текущая доля | Статус |",
            "|---|---|---|",
        ]

        for cl, wt in summary["cluster_breakdown"].items():
            status = "🚨 ПРЕВЫШЕНИЕ" if wt > self.tilt_guard.MAX_CLUSTER_WEIGHT_PCT else "✅ OK"
            lines.append(f"| **{cl}** | {wt:.1f}% | {status} |")

        if summary["cluster_breaches"]:
            lines.append("\n### 🚨 Превышения лимитов кластеров:")
            for cb in summary["cluster_breaches"]:
                lines.append(f"- **{cb['cluster']}**: {cb['weight_pct']}% (лимит {cb['cap_pct']}%, избыток +{cb['excess_pct']}%) ➔ *Остановить набор новых активов в кластере*")

        lines.append("\n## 2. Монитор тильта (Anti-Gemini Revenge Trading Guard)\n")
        if summary["tilt_locks"]:
            lines.append("| Тикер | Проект | PnL | Режим защиты |")
            lines.append("|---|---|---|---|")
            for t in summary["tilt_locks"]:
                lines.append(f"| **{t['symbol']}** | {t['name']} | `{t['pnl']:.1f}%` | 🔒 **TILT LOCK** (запрет усреднения / наращивания) |")
        else:
            lines.append("✅ Позиций в зоне тильт-риска (-15% ... -25%) не обнаружено.\n")

        lines.append("\n## 3. Ревизия недействительных тезисов (Drawdown > 25%)\n")
        if summary["invalidation_alerts"]:
            lines.append("| Тикер | Проект | PnL | Рекомендация |")
            lines.append("|---|---|---|---|")
            for inv in summary["invalidation_alerts"]:
                lines.append(f"| **{inv['symbol']}** | {inv['name']} | `{inv['pnl']:.1f}%` | ⛔ **Thesis Invalidation**: Проверка предпосылок. При поломке тезиса — немедленный выход. |")
        else:
            lines.append("✅ Позиций с критической просадкой (> 25%) нет.\n")

        lines.append("\n## 4. Институциональный регламент опционов и деривативов")
        lines.append("- **Margin Cliff**: Запрещено удерживать фьючерсы под обеспечение опционами за < 48ч до экспирации.")
        lines.append("- **Notional Fee**: Комиссия на опционах считается от полного номинала. Если комиссия > 15% ожидаемого профита — вход заблокирован.")
        lines.append("- **Liquidity Guard**: Если спред Bid-Ask > 20% от прибыли — фиксация только через синтетический дельта-хедж фьючерсом.")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return file_path
