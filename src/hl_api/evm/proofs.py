"""Flexible vault proof utilities."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import requests
from web3 import Web3

from ..exceptions import NetworkError, ValidationError
from ..types import VerificationPayload
from .config import FlexibleVaultConfig
from .connections import Web3Connections

logger = logging.getLogger(__name__)


_VERIFIER_ABI = (
    {
        "inputs": [],
        "name": "merkleRoot",
        "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "stateMutability": "view",
        "type": "function",
    },
)


@dataclass(frozen=True)
class ProofDataset:
    """In-memory representation of a fetched proof blob."""

    url: str
    title: str
    merkle_root: str
    payloads: dict[str, Mapping[str, Any]]


class ProofManager:
    """Fetch proof artifacts and enforce safety checks before usage."""

    def __init__(self, session: requests.Session, *, request_timeout: float) -> None:
        self._session = session
        self._request_timeout = request_timeout
        self._cache: dict[str, ProofDataset] = {}
        self._validated_roots: set[str] = set()

    def fetch(self, config: FlexibleVaultConfig) -> ProofDataset:
        blob = config.proof_blob
        if blob is not None:
            if not isinstance(blob, Mapping):
                raise ValidationError(
                    "Flexible vault proof blob must be a mapping",
                    field="proof_blob",
                    value=blob,
                )

            source_label = config.proof_url or "<inline>"
            if source_label == "<inline>":
                logger.debug("Loading flexible vault proof set from inline blob")
            else:
                logger.debug(
                    "Loading flexible vault proof set from inline blob via %s",
                    source_label,
                )
            dataset = _build_dataset(blob, source_label=source_label)
            if config.proof_url:
                self._cache.setdefault(config.proof_url, dataset)
            return dataset

        url = config.proof_url
        if not url:
            raise ValidationError(
                "Flexible vault proof URL is required when no blob is provided",
                field="proof_url",
                value=url,
            )

        cached = self._cache.get(url)
        if cached is not None:
            return cached

        logger.debug("Fetching flexible vault proof set from %s", url)
        try:
            response = self._session.get(url, timeout=self._request_timeout, allow_redirects=False)
            response.raise_for_status()
            if 300 <= response.status_code < 400:
                raise ValidationError(
                    "Proof source responded with a redirect",
                    field="url",
                    value=url,
                    details={
                        "status": response.status_code,
                        "location": response.headers.get("Location"),
                    },
                )
        except requests.RequestException as exc:  # pragma: no cover - network failure
            raise NetworkError(
                f"Failed to fetch verification proof set from {url}",
                endpoint=url,
                status_code=getattr(exc.response, "status_code", None),
                details={"error": str(exc)},
            ) from exc

        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValidationError(
                "Proof payload is not a JSON object",
                field="payload",
                value=payload,
                details={"url": url},
            )

        dataset = _build_dataset(payload, source_label=url)
        self._cache[url] = dataset
        return dataset

    def ensure_merkle_root(
        self, config: FlexibleVaultConfig, dataset: ProofDataset, connections: Web3Connections
    ) -> None:
        verifier = config.verifier_address
        if not verifier or not config.check_merkle_root:
            return

        cache_key = f"{dataset.url}|{verifier.lower()}"
        if cache_key in self._validated_roots:
            return

        web3 = _select_web3(connections, config.verifier_network)
        address = Web3.to_checksum_address(verifier)
        try:
            contract = web3.eth.contract(address=address, abi=_VERIFIER_ABI)
            onchain_root = contract.functions.merkleRoot().call()
        except Exception as exc:  # pragma: no cover - defensive
            raise NetworkError(
                "Failed to read merkle root from verifier contract",
                endpoint=address,
                details={"error": str(exc)},
            ) from exc

        onchain_hex = Web3.to_hex(onchain_root).lower()
        expected_hex = dataset.merkle_root.lower()
        if onchain_hex != expected_hex:
            raise ValidationError(
                "Merkle root mismatch between on-chain verifier and proof set",
                field="merkle_root",
                value=onchain_hex,
                details={
                    "expected": expected_hex,
                    "verifier": address,
                    "url": dataset.url,
                },
            )

        self._validated_roots.add(cache_key)


def _build_dataset(payload: Mapping[str, Any], *, source_label: str) -> ProofDataset:
    title = _expect_str(payload.get("title"), "title")
    merkle_root = _expect_hex(payload.get("merkle_root"), "merkle_root", expected_bytes=32)
    proofs_raw = payload.get("merkle_proofs")
    if not isinstance(proofs_raw, list):
        raise ValidationError(
            "Proof payload missing merkle_proofs list",
            field="merkle_proofs",
            value=proofs_raw,
        )

    proof_payloads: dict[str, Mapping[str, Any]] = {}
    for entry in proofs_raw:
        if not isinstance(entry, Mapping):
            raise ValidationError(
                "Proof entry must be an object",
                field="merkle_proofs",
                value=entry,
            )
        description = _expect_str(entry.get("description"), "description")
        proof_payloads[description] = dict(entry)

    label = source_label if source_label != "<inline>" else f"inline:{merkle_root}"
    return ProofDataset(url=label, title=title, merkle_root=merkle_root, payloads=proof_payloads)


class FlexibleVaultProofResolver:
    """Coordinate flexible vault proof retrieval and payload construction."""

    def __init__(
        self,
        config: FlexibleVaultConfig,
        connections: Web3Connections,
        session: requests.Session,
        *,
        request_timeout: float,
        proof_manager: ProofManager | None = None,
    ) -> None:
        self._config = config
        self._connections = connections
        self._manager = proof_manager or ProofManager(session, request_timeout=request_timeout)
        self._dataset = self._manager.fetch(config)
        self._manager.ensure_merkle_root(config, self._dataset, connections)

    def resolve(
        self,
        description: str,
        _context: Mapping[str, Any] | None = None,
    ) -> VerificationPayload:
        if not self._config:
            raise ValidationError(
                "Flexible vault proofs are not configured", field="flexible_vault"
            )

        logger.debug(
            "Resolving flexible vault proof for description '%s'",
            description,
        )
        payload = self._dataset.payloads.get(description)
        if payload is None:
            available_payloads = sorted(self._dataset.payloads.keys())
            logger.warning("Proofs available: %s", available_payloads)
            raise ValidationError(
                "No proofs available for configured description",
                field="description",
                value=description,
                details={"available": sorted(self._dataset.payloads.keys())},
            )

        result = VerificationPayload.from_dict(dict(payload))
        logger.debug(
            "Flexible vault proof for description '%s' uses '%s' (url=%s, proof=%s)",
            description,
            self._dataset.url,
            _preview_proof(result),
        )
        return result


def _expect_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"Proof payload missing {field}", field=field, value=value)
    return value


def _expect_hex(value: Any, field: str, *, expected_bytes: int | None = None) -> str:
    raw = _expect_str(value, field)
    if not raw.startswith("0x"):
        raise ValidationError("Expected hex-encoded string", field=field, value=value)
    lowered = raw.lower()
    if expected_bytes is not None and len(lowered) != 2 + expected_bytes * 2:
        raise ValidationError(
            "Unexpected byte length for hex value",
            field=field,
            value=value,
            details={"expected_length": expected_bytes},
        )
    return lowered


def _preview_proof(payload: VerificationPayload) -> str:
    if payload.proof:
        first = payload.proof[0]
        if isinstance(first, bytes):
            return Web3.to_hex(first)
        return str(first)
    return "<empty>"


def _select_web3(connections: Web3Connections, network_label: str | None) -> Web3:
    label = (network_label or "hyper").strip().lower()
    if label in {"hyper", "hyperliquid", "hl"}:
        return connections.hyperliquid_web3
    if label in {"mainnet", "ethereum", "eth"}:
        return connections.mainnet_web3
    raise ValidationError("Unknown proof source network", field="network", value=network_label)


__all__ = ["FlexibleVaultProofResolver", "ProofDataset", "ProofManager"]
