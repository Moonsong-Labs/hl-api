"""Flexible vault proof utilities."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import requests
from web3 import Web3

from ..exceptions import NetworkError, ValidationError
from ..types import VerificationPayload
from .config import EVMClientConfig
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

    def fetch(self, config: EVMClientConfig) -> dict[str, ProofDataset]:
        """Fetch and return multiple proof datasets indexed by title."""
        datasets: dict[str, ProofDataset] = {}

        # Handle inline blobs
        blob = config.flexible_vault_proof_blob
        if blob is not None:
            # Normalize to sequence
            blobs: Sequence[Mapping[str, Any]]
            if isinstance(blob, Sequence) and not isinstance(blob, (str, bytes)):
                blobs = blob
            elif isinstance(blob, Mapping):
                blobs = [blob]
            else:
                raise ValidationError(
                    "Flexible vault proof blob must be a mapping or sequence of mappings",
                    field="proof_blob",
                    value=blob,
                )

            for i, single_blob in enumerate(blobs):
                if not isinstance(single_blob, Mapping):
                    raise ValidationError(
                        f"Proof blob at index {i} must be a mapping",
                        field="proof_blob",
                        value=single_blob,
                    )

                source_label = f"<inline-{i}>"
                logger.debug("Loading flexible vault proof set from inline blob %d", i)
                dataset = _build_dataset(single_blob, source_label=source_label)

                if dataset.title in datasets:
                    raise ValidationError(
                        f"Duplicate proof dataset title: {dataset.title}",
                        field="title",
                        value=dataset.title,
                        details={"source": source_label},
                    )
                datasets[dataset.title] = dataset

        # Handle URLs
        url = config.flexible_vault_proof_url
        if url:
            # Normalize to sequence
            urls: Sequence[str]
            if isinstance(url, str):
                urls = [url]
            elif isinstance(url, Sequence):
                urls = url
            else:
                raise ValidationError(
                    "Flexible vault proof URL must be a string or sequence of strings",
                    field="proof_url",
                    value=url,
                )

            for single_url in urls:
                # Check cache first
                cached = self._cache.get(single_url)
                if cached is not None:
                    if cached.title in datasets:
                        raise ValidationError(
                            f"Duplicate proof dataset title: {cached.title}",
                            field="title",
                            value=cached.title,
                            details={"url": single_url},
                        )
                    datasets[cached.title] = cached
                    continue

                logger.debug("Fetching flexible vault proof set from %s", single_url)
                try:
                    response = self._session.get(
                        single_url, timeout=self._request_timeout, allow_redirects=False
                    )
                    response.raise_for_status()
                    if 300 <= response.status_code < 400:
                        raise ValidationError(
                            "Proof source responded with a redirect",
                            field="url",
                            value=single_url,
                            details={
                                "status": response.status_code,
                                "location": response.headers.get("Location"),
                            },
                        )
                except requests.RequestException as exc:  # pragma: no cover - network failure
                    raise NetworkError(
                        f"Failed to fetch verification proof set from {single_url}",
                        endpoint=single_url,
                        status_code=getattr(exc.response, "status_code", None),
                        details={"error": str(exc)},
                    ) from exc

                payload = response.json()
                if not isinstance(payload, Mapping):
                    raise ValidationError(
                        "Proof payload is not a JSON object",
                        field="payload",
                        value=payload,
                        details={"url": single_url},
                    )

                dataset = _build_dataset(payload, source_label=single_url)
                self._cache[single_url] = dataset

                if dataset.title in datasets:
                    raise ValidationError(
                        f"Duplicate proof dataset title: {dataset.title}",
                        field="title",
                        value=dataset.title,
                        details={"url": single_url},
                    )
                datasets[dataset.title] = dataset

        if not datasets:
            raise ValidationError(
                "No proof datasets provided via blob or URL",
                field="flexible_vault",
                value=None,
            )

        return datasets

    def ensure_merkle_root(
        self, config: EVMClientConfig, dataset: ProofDataset, connections: Web3Connections
    ) -> None:
        verifier = config.flexible_vault_verifier_address
        if not verifier or not config.flexible_vault_check_merkle_root:
            return

        cache_key = f"{dataset.url}|{verifier.lower()}"
        if cache_key in self._validated_roots:
            return

        web3 = _select_web3(connections, config.flexible_vault_verifier_network)
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
        config: EVMClientConfig,
        connections: Web3Connections,
        session: requests.Session,
        *,
        request_timeout: float,
        proof_manager: ProofManager | None = None,
    ) -> None:
        self._config = config
        self._connections = connections
        self._manager = proof_manager or ProofManager(session, request_timeout=request_timeout)
        self._datasets = self._manager.fetch(config)
        # Validate merkle roots for all datasets
        for dataset in self._datasets.values():
            self._manager.ensure_merkle_root(config, dataset, connections)

    def resolve(
        self,
        description: str,
        json_name: str,
        _context: Mapping[str, Any] | None = None,
    ) -> VerificationPayload:
        if not self._config:
            raise ValidationError(
                "Flexible vault proofs are not configured", field="flexible_vault"
            )

        # Find dataset by json_name (which matches title)
        dataset = self._datasets.get(json_name)
        if dataset is None:
            available_titles = sorted(self._datasets.keys())
            raise ValidationError(
                f"No proof dataset found with title '{json_name}'",
                field="json_name",
                value=json_name,
                details={"available_titles": available_titles},
            )

        logger.debug(
            "Resolving flexible vault proof for description '%s' from dataset '%s'",
            description,
            json_name,
        )
        payload = dataset.payloads.get(description)
        if payload is None:
            available_payloads = sorted(dataset.payloads.keys())
            logger.warning("Proofs available in dataset '%s': %s", json_name, available_payloads)
            raise ValidationError(
                f"No proofs available for description '{description}' in dataset '{json_name}'",
                field="description",
                value=description,
                details={"available": available_payloads, "dataset": json_name},
            )

        result = VerificationPayload.from_dict(dict(payload))
        logger.debug(
            "Flexible vault proof for description '%s' from dataset '%s' (url=%s, proof=%s)",
            description,
            json_name,
            dataset.url,
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
