from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "PackageProof Pro"
    environment: str = "development"
    database_url: str = "sqlite:///./data/packageproof.db"

    x402_enabled: bool = False
    x402_network: Literal["testnet", "mainnet"] = "testnet"
    pay_to_address: str = ""
    facilitator_url: str = "https://facilitator.goplausible.xyz"
    x402_asset_id: str = ""
    x402_asset_symbol: str = "USDC"
    x402_asset_decimals: int = 6
    x402_challenge_tag: str = "x402-global-challenge"
    analyze_package_price: str = "$0.05"

    e2b_api_key: str = ""
    enable_e2b: bool = True
    e2b_allow_internet_access: bool = True
    e2b_install_strace: bool = True
    e2b_template: str | None = None
    e2b_timeout_seconds: int = Field(default=90, ge=10, le=300)

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4.1-mini"

    cache_ttl_seconds: int = 60 * 60 * 24
    http_timeout_seconds: float = 15.0
    max_archive_bytes: int = 8 * 1024 * 1024
    max_static_files: int = 250

    @property
    def payment_configured(self) -> bool:
        if not self.pay_to_address or not self.facilitator_url:
            return False

        try:
            from x402.mechanisms.avm import is_valid_address

            return is_valid_address(self.pay_to_address)
        except ImportError:
            return False

    @property
    def x402_network_caip2(self) -> str:
        from x402.mechanisms.avm import ALGORAND_MAINNET_CAIP2, ALGORAND_TESTNET_CAIP2

        return (
            ALGORAND_MAINNET_CAIP2
            if self.x402_network == "mainnet"
            else ALGORAND_TESTNET_CAIP2
        )

    @property
    def resolved_x402_asset_id(self) -> str:
        from x402.mechanisms.avm import USDC_MAINNET_ASA_ID, USDC_TESTNET_ASA_ID

        expected = str(
            USDC_MAINNET_ASA_ID if self.x402_network == "mainnet" else USDC_TESTNET_ASA_ID
        )
        if self.x402_asset_id and self.x402_asset_id != expected:
            raise ValueError(
                f"X402_ASSET_ID must be {expected} for Algorand {self.x402_network} USDC"
            )
        return expected

    @cached_property
    def sqlite_path(self) -> Path:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("Phase 1 supports sqlite database URLs only")
        return Path(self.database_url.removeprefix(prefix)).resolve()
