from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from fastapi import FastAPI

from packageproof.core.config import Settings

logger = logging.getLogger(__name__)


def configure_x402_payments(app: FastAPI, settings: Settings) -> None:
    if not settings.x402_enabled:
        logger.info("x402 middleware disabled by configuration")
        return

    if not settings.payment_configured:
        raise RuntimeError(
            "x402 is enabled but PAY_TO_ADDRESS is not a valid Algorand address "
            "or FACILITATOR_URL is missing"
        )

    try:
        from x402.extensions.bazaar import OutputConfig, declare_discovery_extension
        from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
        from x402.http.middleware.fastapi import PaymentMiddlewareASGI
        from x402.http.types import RouteConfig
        from x402.mechanisms.avm.exact import ExactAvmServerScheme
        from x402.schemas import AssetAmount
        from x402.server import x402ResourceServer
    except ImportError as exc:
        raise RuntimeError("official x402-avm SDK is required when x402 is enabled") from exc

    facilitator = HTTPFacilitatorClient(
        FacilitatorConfig(url=settings.facilitator_url)
    )

    server = x402ResourceServer(facilitator)
    server.register("algorand:*", ExactAvmServerScheme())

    try:
        price_decimal = Decimal(settings.analyze_package_price.removeprefix("$"))
        atomic_price = price_decimal * (Decimal(10) ** settings.x402_asset_decimals)
    except InvalidOperation as exc:
        raise RuntimeError("ANALYZE_PACKAGE_PRICE must be a decimal USD amount") from exc
    if price_decimal <= 0 or atomic_price != atomic_price.to_integral_value():
        raise RuntimeError(
            "ANALYZE_PACKAGE_PRICE must be positive and exactly representable in USDC units"
        )

    payment_asset = AssetAmount(
        amount=str(int(atomic_price)),
        asset=settings.resolved_x402_asset_id,
        # x402-avm 2.0.2 builds PaymentRequirements.extra from AssetAmount.extra;
        # PaymentOption.extra is currently not merged by its HTTP adapter.
        extra={
            "name": settings.x402_asset_symbol,
            "decimals": settings.x402_asset_decimals,
            "tag": settings.x402_challenge_tag,
        },
    )

    discovery = declare_discovery_extension(
        input={
            "ecosystem": "npm",
            "package": "lodash",
            "version": "latest",
            "analysis_depth": "quick",
            "include_ai_summary": False,
        },
        input_schema={
            "type": "object",
            "properties": {
                "ecosystem": {"type": "string", "enum": ["npm", "pypi"]},
                "package": {"type": "string", "minLength": 1},
                "version": {"type": "string", "default": "latest"},
                "analysis_depth": {
                    "type": "string",
                    "enum": ["quick", "standard", "deep"],
                    "default": "standard",
                },
                "include_ai_summary": {"type": "boolean", "default": True},
            },
            "required": ["ecosystem", "package"],
            "additionalProperties": False,
        },
        body_type="json",
        output=OutputConfig(
            example={
                "report_id": "rpt_example",
                "verdict": "allow",
                "risk_score": 4,
                "agent_action": "install_allowed",
                "attack_types": [],
                "summary": "No high-risk package behavior detected.",
            },
            schema={
                "type": "object",
                "properties": {
                    "report_id": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["allow", "review", "block"]},
                    "risk_score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "agent_action": {"type": "string"},
                    "attack_types": {"type": "array", "items": {"type": "string"}},
                    "summary": {"type": "string"},
                },
                "required": ["report_id", "verdict", "risk_score", "agent_action"],
            },
        ),
    )

    routes = {
        "POST /v1/analyze-package": RouteConfig(
            accepts=PaymentOption(
                scheme="exact",
                price=payment_asset,
                network=settings.x402_network_caip2,
                pay_to=settings.pay_to_address,
                max_timeout_seconds=300,
            ),
            description=(
                "PackageProof Pro analyzes an npm or PyPI package and returns an auditable "
                "risk score, allow/review/block verdict, attack classifications, and evidence."
            ),
            mime_type="application/json",
            extensions=discovery,
        )
    }
    app.add_middleware(
        PaymentMiddlewareASGI,
        routes=routes,
        server=server,
    )
    logger.info(
        "Algorand x402 middleware enabled for POST /v1/analyze-package on %s (USDC ASA %s)",
        settings.x402_network,
        settings.resolved_x402_asset_id,
    )
