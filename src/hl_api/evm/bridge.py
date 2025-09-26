"""CCTPv2 bridging logic for the HyperLiquid EVM client."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any

import requests

from ..exceptions import NetworkError, ValidationError
from ..types import BridgeDirection, Response, VerificationPayload
from ..utils import serialise_receipt
from .config import EVMClientConfig
from .connections import Web3Connections
from .proofs import FlexibleVaultProofResolver

logger = logging.getLogger(__name__)

USDC_SCALING = Decimal("1000000")

_CCTP_VERIFICATION_DESCRIPTIONS = (
    "USDC.approve(TokenMessenger, anyInt)",
    "TokenMessenger.depositForBurn(anyInt)",
)


class CCTPBridge:
    """Helper responsible for orchestrating CCTPv2 burns and claims."""

    def __init__(
        self,
        config: EVMClientConfig,
        connections: Web3Connections,
        session: requests.Session,
        *,
        verification_resolver: FlexibleVaultProofResolver | None = None,
        disable_call_verification: bool = False,
    ) -> None:
        self._config = config
        self._connections = connections
        self._session = session
        self._wait_for_receipt = config.wait_for_receipt
        self._receipt_timeout = config.receipt_timeout
        self._iris_base_url = config.iris_base_url or ""
        self._iris_poll_interval = config.iris_poll_interval
        self._iris_max_polls = config.iris_max_polls
        self._hyper_domain = (
            config.hyperliquid_domain if config.hyperliquid_domain is not None else 19
        )
        self._mainnet_domain = config.mainnet_domain if config.mainnet_domain is not None else 0
        self._cctp_finality_threshold = config.cctp_finality_threshold
        self._verification_resolver = verification_resolver
        self._call_verification_disabled = disable_call_verification

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    def bridge_mainnet_to_hyperliquid(
        self,
        amount: float,
        *,
        max_fee: int | None = None,
        min_finality_threshold: int | None = None,
    ) -> Response:
        try:
            source_contract = self._connections.ensure_bridge_contract("mainnet")
            destination_contract = self._connections.ensure_bridge_contract("hyper")
        except (ValidationError, NetworkError) as exc:
            return Response(
                success=False,
                error=str(exc),
                raw_response={
                    "direction": "mainnet_to_hyper",
                    "error_details": getattr(exc, "details", {}),
                },
            )

        return self._bridge_via_cctp(
            amount=amount,
            source_contract=source_contract,
            destination_contract=destination_contract,
            source_domain=self._mainnet_domain,
            destination_domain=self._hyper_domain,
            direction=BridgeDirection.MAINNET_TO_HYPER,
            max_fee_override=max_fee,
            min_finality_threshold=min_finality_threshold,
            source_web3=self._connections.mainnet_web3,
            destination_web3=self._connections.hyperliquid_web3,
        )

    def bridge_hyperliquid_to_mainnet(
        self,
        amount: float,
        *,
        max_fee: int | None = None,
        min_finality_threshold: int | None = None,
    ) -> Response:
        try:
            source_contract = self._connections.ensure_bridge_contract("hyper")
            destination_contract = self._connections.ensure_bridge_contract("mainnet")
        except (ValidationError, NetworkError) as exc:
            return Response(
                success=False,
                error=str(exc),
                raw_response={
                    "direction": "hyper_to_mainnet",
                    "error_details": getattr(exc, "details", {}),
                },
            )

        return self._bridge_via_cctp(
            amount=amount,
            source_contract=source_contract,
            destination_contract=destination_contract,
            source_domain=self._hyper_domain,
            destination_domain=self._mainnet_domain,
            direction=BridgeDirection.HYPER_TO_MAINNET,
            max_fee_override=max_fee,
            min_finality_threshold=min_finality_threshold,
            source_web3=self._connections.hyperliquid_web3,
            destination_web3=self._connections.mainnet_web3,
        )

    # ------------------------------------------------------------------
    # Internal workflow
    # ------------------------------------------------------------------
    def _bridge_via_cctp(
        self,
        *,
        amount: float,
        source_contract,
        destination_contract,
        source_domain: int,
        destination_domain: int,
        direction: BridgeDirection,
        max_fee_override: int | None,
        min_finality_threshold: int | None,
        source_web3,
        destination_web3,
    ) -> Response:
        raw_context: dict[str, Any] = {
            "direction": direction.value,
            "source_domain": source_domain,
            "destination_domain": destination_domain,
        }

        try:
            amount_units, amount_decimal, truncated = self._normalise_usdc_amount(amount)
        except ValidationError as exc:
            logger.debug("Stage CCTP [%s]: bridge aborted (reason=%s)", direction, str(exc))
            return Response(
                success=False,
                error=str(exc),
                raw_response={
                    **raw_context,
                    "field": exc.field,
                    "value": exc.value,
                    "details": exc.details,
                },
            )

        if truncated:
            logger.warning(
                "Truncating bridge amount to 6 decimals (%s request on %s)", amount, direction
            )

        amount_float = float(amount_decimal)
        raw_context["amount_units"] = amount_units
        logger.debug(
            "Stage CCTP [%s]: prepare amount (amount=%.6f, units=%s)",
            direction,
            amount_float,
            amount_units,
        )

        if max_fee_override is not None and max_fee_override < 0:
            logger.debug(
                "Stage CCTP [%s]: bridge aborted (reason=max_fee must be non-negative)", direction
            )
            return Response(
                success=False,
                amount=amount_float,
                error="max_fee must be non-negative",
                raw_response={**raw_context, "max_fee": max_fee_override},
            )

        finality_threshold = (
            min_finality_threshold
            if min_finality_threshold is not None
            else self._cctp_finality_threshold
        )
        raw_context["finality_threshold"] = finality_threshold
        if finality_threshold <= 0:
            logger.debug(
                "Stage CCTP [%s]: bridge aborted (reason=Finality threshold must be positive)",
                direction,
            )
            return Response(
                success=False,
                amount=amount_float,
                error="Finality threshold must be positive",
                raw_response=raw_context,
            )

        logger.debug(
            "Stage CCTP [%s]: fetch fee quote (source=%s, dest=%s)",
            direction,
            source_domain,
            destination_domain,
        )
        try:
            max_fee = (
                max_fee_override
                if max_fee_override is not None
                else self._fetch_cctp_fee(amount_units, source_domain, destination_domain)
            )
        except ValidationError as exc:
            logger.debug("Stage CCTP [%s]: bridge aborted (reason=%s)", direction, str(exc))
            return Response(
                success=False,
                amount=amount_float,
                error=str(exc),
                raw_response={
                    **raw_context,
                    "field": exc.field,
                    "value": exc.value,
                    "details": exc.details,
                },
            )
        except requests.RequestException as exc:
            logger.error("Failed to fetch CCTP fee quote: %s", exc)
            logger.debug(
                "Stage CCTP [%s]: bridge aborted (reason=%s)",
                direction,
                f"Failed to fetch CCTP fee quote: {exc}",
            )
            return Response(
                success=False,
                amount=amount_float,
                error=f"Failed to fetch CCTP fee quote: {exc}",
                raw_response=raw_context,
            )

        raw_context["max_fee"] = max_fee
        if max_fee >= amount_units:
            logger.debug(
                "Stage CCTP [%s]: bridge aborted (reason=%s)",
                direction,
                "Quoted max fee exceeds or equals bridge amount",
            )
            return Response(
                success=False,
                amount=amount_float,
                error="Quoted max fee exceeds or equals bridge amount",
                raw_response=raw_context,
            )

        payloads = self._resolve_cctp_verification_payloads(direction, amount_units)

        logger.debug("Stage CCTP [%s]: submit burn transaction", direction)
        try:
            burn_tx = source_contract.functions.bridgeUSDCViaCCTPv2(
                amount_units,
                max_fee,
                finality_threshold,
                payloads,
            ).transact()
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to submit CCTP burn on %s", direction)
            logger.debug("Stage CCTP [%s]: bridge aborted (reason=%s)", direction, str(exc))
            return Response(
                success=False,
                amount=amount_float,
                error=str(exc),
                raw_response=raw_context,
            )

        burn_tx_hash = burn_tx.to_0x_hex()
        logger.debug("Stage CCTP [%s]: burn submitted (tx=%s)", direction, burn_tx_hash)
        burn_receipt = (
            source_web3.eth.wait_for_transaction_receipt(burn_tx, timeout=self._receipt_timeout)
            if self._wait_for_receipt
            else None
        )
        burn_receipt_data = serialise_receipt(burn_receipt) if burn_receipt else None
        if burn_receipt_data is not None:
            raw_context["burn_receipt"] = burn_receipt_data

        try:
            message, attestation = self._poll_iris_attestation(
                direction, source_domain, burn_tx_hash
            )
        except TimeoutError as exc:
            logger.error("IRIS attestation timed out for %s", direction)
            logger.debug("Stage CCTP [%s]: bridge aborted (reason=%s)", direction, str(exc))
            return Response(
                success=False,
                amount=amount_float,
                burn_tx_hash=burn_tx_hash,
                error=str(exc),
                raw_response=raw_context,
            )
        except ValidationError as exc:
            logger.error("IRIS attestation failed for %s: %s", direction, exc)
            logger.debug("Stage CCTP [%s]: bridge aborted (reason=%s)", direction, str(exc))
            return Response(
                success=False,
                amount=amount_float,
                burn_tx_hash=burn_tx_hash,
                error=str(exc),
                raw_response={
                    **raw_context,
                    "field": exc.field,
                    "value": exc.value,
                    "details": exc.details,
                },
            )

        logger.debug("Stage CCTP [%s]: submit claim transaction", direction)
        try:
            claim_tx = destination_contract.functions.receiveUSDCViaCCTPv2(
                message, attestation
            ).transact()
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to submit CCTP claim on %s", direction)
            logger.debug("Stage CCTP [%s]: bridge aborted (reason=%s)", direction, str(exc))
            return Response(
                success=False,
                amount=amount_float,
                burn_tx_hash=burn_tx_hash,
                message=message,
                attestation=attestation,
                error=str(exc),
                raw_response=raw_context,
            )

        claim_tx_hash = claim_tx.to_0x_hex()
        logger.debug("Stage CCTP [%s]: claim submitted (tx=%s)", direction, claim_tx_hash)
        claim_receipt = (
            destination_web3.eth.wait_for_transaction_receipt(
                claim_tx, timeout=self._receipt_timeout
            )
            if self._wait_for_receipt
            else None
        )
        claim_receipt_data = serialise_receipt(claim_receipt) if claim_receipt else None
        if claim_receipt_data is not None:
            raw_context["claim_receipt"] = claim_receipt_data

        logger.debug(
            "Stage CCTP [%s]: bridge complete (burn_tx=%s, claim_tx=%s)",
            direction,
            burn_tx_hash,
            claim_tx_hash,
        )
        return Response(
            success=True,
            amount=float(Decimal(amount_units) / USDC_SCALING),
            burn_tx_hash=burn_tx_hash,
            claim_tx_hash=claim_tx_hash,
            message=message,
            attestation=attestation,
            raw_response=raw_context,
        )

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------
    def _normalise_usdc_amount(self, amount: float | str | Decimal) -> tuple[int, Decimal, bool]:
        if isinstance(amount, Decimal):
            quantity = amount
        else:
            try:
                quantity = Decimal(str(amount))
            except (ValueError, InvalidOperation) as exc:
                raise ValidationError(
                    "Invalid USDC amount",
                    field="amount",
                    value=amount,
                    details={"error": str(exc)},
                ) from exc

        if quantity <= 0:
            raise ValidationError(
                "Bridge amount must be positive", field="amount", value=float(quantity)
            )

        scaled_decimal = quantity * USDC_SCALING
        scaled_integral = scaled_decimal.to_integral_value(rounding=ROUND_DOWN)
        truncated = scaled_integral != scaled_decimal

        return int(scaled_integral), scaled_integral / USDC_SCALING, truncated

    def _resolve_cctp_verification_payloads(
        self, direction: BridgeDirection, amount_units: int
    ) -> list[tuple[int, bytes, list[bytes]]]:
        if self._call_verification_disabled:
            logger.debug(
                "Call verification disabled; using default CCTP verification payloads for '%s'",
                direction,
            )
            return [
                VerificationPayload.default().as_tuple() for _ in _CCTP_VERIFICATION_DESCRIPTIONS
            ]

        resolver = self._verification_resolver
        if resolver is None:
            logger.warning(
                "No verification resolver configured; using default CCTP payloads for '%s'",
                direction,
            )
            return [
                VerificationPayload.default().as_tuple() for _ in _CCTP_VERIFICATION_DESCRIPTIONS
            ]

        context = {"direction": direction.value, "amount_units": amount_units}

        json_name = None
        if hasattr(resolver, "_datasets"):
            if direction == BridgeDirection.MAINNET_TO_HYPER:
                for title in resolver._datasets.keys():
                    if "mainnet" in title.lower() or "ethereum" in title.lower():
                        json_name = title
                        break
            elif direction == BridgeDirection.HYPER_TO_MAINNET:
                for title in resolver._datasets.keys():
                    if "hyperevm" in title.lower() or "hyperliquid" in title.lower():
                        json_name = title
                        break
            else:
                raise ValidationError(
                    "Unknown bridge direction",
                    field="direction",
                    value=direction,
                )

            # If no specific match found, use the first available dataset
            if not json_name and resolver._datasets:
                json_name = next(iter(resolver._datasets.keys()))

        if not json_name:
            json_name = "default"

        return [
            resolver.resolve(desc, json_name, context).as_tuple()
            for desc in _CCTP_VERIFICATION_DESCRIPTIONS
        ]

    def _fetch_cctp_fee(self, amount_units: int, src_domain: int, dest_domain: int) -> int:
        url = f"{self._iris_base_url}/v2/burn/USDC/fees/{src_domain}/{dest_domain}"
        logger.debug("Fetching CCTP fee quote from IRIS: %s", url)
        response = self._session.get(url, timeout=self._config.request_timeout)
        response.raise_for_status()
        json_resp = response.json()

        if not isinstance(json_resp, list):
            raise ValidationError(
                "Unexpected fee response format",
                field="iris_response",
                value=json_resp,
            )

        entries = [entry for entry in json_resp if isinstance(entry, Mapping)]
        if not entries:
            logger.warning(
                "Fee response missing usable entries for domains %s -> %s", src_domain, dest_domain
            )
            return 0

        chosen = next(
            (
                entry
                for entry in entries
                if entry.get("finalityThreshold") == self._cctp_finality_threshold
            ),
            entries[0],
        )

        try:
            bps = int(chosen.get("minimumFee", 0))
        except (TypeError, ValueError):
            bps = 0

        fee = (amount_units * bps + 9999) // 10000
        logger.info(
            "CCTP fee quote %s -> %s: bps=%s maxFee=%s",
            src_domain,
            dest_domain,
            bps,
            fee,
        )
        return fee

    def _poll_iris_attestation(
        self, direction: BridgeDirection, domain: int, tx_hash: str
    ) -> tuple[str, str]:
        url = f"{self._iris_base_url}/v2/messages/{domain}?transactionHash={tx_hash}"
        logger.debug(
            "Stage CCTP [%s]: poll IRIS (domain=%s, tx=%s, max_polls=%s, interval=%s)",
            direction,
            domain,
            tx_hash,
            self._iris_max_polls,
            self._iris_poll_interval,
        )

        for attempt in range(self._iris_max_polls):
            try:
                response = self._session.get(url, timeout=self._config.request_timeout)
            except requests.RequestException as exc:  # pragma: no cover - network flake
                logger.debug(
                    "IRIS poll error (attempt %s/%s): %s", attempt + 1, self._iris_max_polls, exc
                )
                time.sleep(self._iris_poll_interval)
                continue

            if response.status_code == 404:
                logger.debug(
                    "IRIS attestation not yet available (404) for %s on attempt %s/%s",
                    tx_hash,
                    attempt + 1,
                    self._iris_max_polls,
                )
                time.sleep(self._iris_poll_interval)
                continue

            response.raise_for_status()
            json_resp = response.json()
            messages = self._extract_iris_messages(json_resp)
            if messages:
                for record in messages:
                    status = str(record.get("status", "")).lower()
                    if status and status != "complete":
                        logger.debug(
                            "IRIS attestation still %s for %s (attempt %s/%s)",
                            status,
                            tx_hash,
                            attempt + 1,
                            self._iris_max_polls,
                        )
                        continue

                    message = record.get("message")
                    attestation = record.get("attestation")
                    if isinstance(message, str) and isinstance(attestation, str):
                        return message, attestation

            time.sleep(self._iris_poll_interval)

        raise TimeoutError(
            f"Timed out waiting for IRIS attestation after {self._iris_max_polls * self._iris_poll_interval:.0f} seconds"
        )

    def _extract_iris_messages(self, json_blob: Any) -> list[Mapping[str, Any]]:
        if isinstance(json_blob, Mapping):
            direct = json_blob.get("messages")
            if isinstance(direct, list):
                return [entry for entry in direct if isinstance(entry, Mapping)]
            data = json_blob.get("data")
            if isinstance(data, Mapping):
                nested = data.get("messages")
                if isinstance(nested, list):
                    return [entry for entry in nested if isinstance(entry, Mapping)]
        return []
