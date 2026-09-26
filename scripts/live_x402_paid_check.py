from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
from typing import Any

import requests
from algosdk import account, encoding, mnemonic
from x402 import max_amount, x402ClientSync
from x402.http import decode_payment_response_header
from x402.http.clients.requests import wrapRequestsWithPayment
from x402.mechanisms.avm import ALGORAND_MAINNET_CAIP2, ALGORAND_TESTNET_CAIP2
from x402.mechanisms.avm.exact import register_exact_avm_client


def load_env_file(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class MnemonicSigner:
    def __init__(self, words: str) -> None:
        self._private_key = mnemonic.to_private_key(words)
        self._address = account.address_from_private_key(self._private_key)

    @property
    def address(self) -> str:
        return self._address

    def sign_transactions(
        self,
        unsigned_txns: list[bytes],
        indexes_to_sign: list[int],
    ) -> list[bytes | None]:
        signed: list[bytes | None] = []
        for index, txn_bytes in enumerate(unsigned_txns):
            if index not in indexes_to_sign:
                signed.append(None)
                continue
            txn = encoding.msgpack_decode(txn_bytes)
            signed_txn = txn.sign(self._private_key)
            signed.append(base64.b64decode(encoding.msgpack_encode(signed_txn)))
        return signed


def build_session(words: str, network: str) -> tuple[requests.Session, str]:
    signer = MnemonicSigner(words)
    client = x402ClientSync()
    register_exact_avm_client(
        client,
        signer,
        networks=network,
        policies=[max_amount(100_000)],  # hard cap: 0.10 USDC
    )
    return wrapRequestsWithPayment(requests.Session(), client), signer.address


def package_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "ecosystem": args.ecosystem,
        "package": args.package,
        "version": args.version,
        "analysis_depth": args.depth,
        "include_ai_summary": args.ai,
    }


def inference_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "model": args.model,
        "messages": [{"role": "user", "content": args.prompt}],
        "stream": False,
    }


def main() -> None:
    load_env_file()
    parser = argparse.ArgumentParser(
        description="Run one capped Algorand x402 v2 paid request against either service."
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--service", choices=["package", "inference"], required=True)
    parser.add_argument(
        "--network",
        choices=["testnet", "mainnet"],
        default=os.getenv("X402_NETWORK", "testnet"),
    )
    parser.add_argument("--allow-mainnet", action="store_true")
    parser.add_argument("--ecosystem", default="npm")
    parser.add_argument("--package", default="lodash")
    parser.add_argument("--version", default="latest")
    parser.add_argument("--depth", default="quick")
    parser.add_argument("--ai", action="store_true")
    parser.add_argument("--model", default="auto")
    parser.add_argument("--prompt", default="Reply with one sentence about Algorand.")
    args = parser.parse_args()

    if args.network == "mainnet" and not args.allow_mainnet:
        raise SystemExit("MainNet payment refused: add --allow-mainnet intentionally.")

    words = os.getenv("ALGORAND_MNEMONIC", "").strip()
    if not words:
        raise SystemExit("Missing ALGORAND_MNEMONIC in the local environment or ignored .env file.")

    network = (
        ALGORAND_MAINNET_CAIP2 if args.network == "mainnet" else ALGORAND_TESTNET_CAIP2
    )
    session, signer_address = build_session(words, network)

    expected_address = os.getenv("AVM_ADDRESS", "").strip()
    if expected_address and signer_address != expected_address:
        raise SystemExit("ALGORAND_MNEMONIC does not derive the configured AVM_ADDRESS.")

    payload = package_payload(args) if args.service == "package" else inference_payload(args)
    response = session.post(args.url, json=payload, timeout=240)

    settlement_header = response.headers.get("PAYMENT-RESPONSE") or response.headers.get(
        "X-PAYMENT-RESPONSE"
    )
    settlement = None
    if settlement_header:
        decoded = decode_payment_response_header(settlement_header)
        settlement = decoded.model_dump(by_alias=True, exclude_none=True)

    try:
        body: Any = response.json()
    except ValueError:
        body = {"text": response.text[:1000]}

    print(
        json.dumps(
            {
                "status_code": response.status_code,
                "url": args.url,
                "service": args.service,
                "network": args.network,
                "payer": signer_address,
                "settlement": settlement,
                "body": body,
            },
            indent=2,
            default=str,
        )
    )

    if response.status_code != 200 or settlement is None:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
