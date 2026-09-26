from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from packageproof.models.schemas import (
    AnalyzeManifestRequest,
    AnalyzeManifestResponse,
    AnalyzePackageRequest,
    AnalyzePackageResponse,
    HealthResponse,
)
from packageproof.services.analyzer import ManifestAnalyzer, PackageAnalyzer

router = APIRouter()


@router.get("/")
async def service_manifest(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    return {
        "service": settings.app_name,
        "version": "0.2.0",
        "description": "Algorand x402-paid npm and PyPI dependency risk analysis.",
        "payment": {
            "protocol": "x402-v2",
            "network": settings.x402_network,
            "caip2": settings.x402_network_caip2,
            "asset": {"symbol": settings.x402_asset_symbol, "id": settings.resolved_x402_asset_id},
            "facilitator": settings.facilitator_url,
            "challenge_tag": settings.x402_challenge_tag,
        },
        "endpoints": [
            {"method": "GET", "path": "/health", "paid": False},
            {"method": "POST", "path": "/v1/analyze-package", "paid": True},
            {"method": "POST", "path": "/v1/analyze-manifest", "paid": False},
            {"method": "GET", "path": "/v1/reports/{report_id}", "paid": False},
        ],
    }


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        payment_configured=settings.payment_configured,
        x402_enabled=settings.x402_enabled,
        x402_network=settings.x402_network,
        x402_asset_id=settings.resolved_x402_asset_id,
    )


@router.post("/v1/analyze-package", response_model=AnalyzePackageResponse)
async def analyze_package(
    payload: AnalyzePackageRequest,
    request: Request,
) -> AnalyzePackageResponse:
    analyzer = PackageAnalyzer(
        settings=request.app.state.settings,
        report_store=request.app.state.report_store,
    )
    try:
        return await analyzer.analyze(payload)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"analysis failed: {exc}") from exc


@router.post("/v1/analyze-manifest", response_model=AnalyzeManifestResponse)
async def analyze_manifest(
    payload: AnalyzeManifestRequest,
    request: Request,
) -> AnalyzeManifestResponse:
    analyzer = ManifestAnalyzer(
        settings=request.app.state.settings,
        report_store=request.app.state.report_store,
    )
    try:
        return await analyzer.analyze(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"invalid manifest JSON: {exc.msg}") from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"manifest analysis failed: {exc}") from exc


@router.get("/v1/reports/{report_id}", response_model=AnalyzePackageResponse)
async def get_report(report_id: str, request: Request) -> AnalyzePackageResponse:
    report = request.app.state.report_store.get(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return report
