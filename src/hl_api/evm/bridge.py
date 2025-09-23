"""CCTPv2 bridging logic for the HyperLiquid EVM client."""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Any

import requests
from web3 import Web3

from ..exceptions import NetworkError, ValidationError
from ..types import BridgeResponse, VerificationPayload
from ..evm_utils import serialise_receipt
from .config import BridgeConfig, EVMClientConfig
from .connections import Web3Connections

logger = logging.getLogger(__name__)

USDC_SCALING = Decimal("1000000")


class CCTPBridge:
    """Helper responsible for orchestrating CCTPv2 burns and claims."""

    def __init__(
        self,
        config: EVMClientConfig,
        connections: Web3Connections,
        session: requests.Session,
    ) -> None:
        bridge_cfg: BridgeConfig = config.bridge
        self._config = config
        self._connections = connections
        self._session = session
        self._wait_for_receipt = bridge_cfg.wait_for_receipt
        self._receipt_timeout = bridge_cfg.receipt_timeout
        self._iris_base_url = bridge_cfg.iris_base_url or ""
        self._iris_poll_interval = bridge_cfg.iris_poll_interval
        self._iris_max_polls = bridge_cfg.iris_max_polls
        self._hyper_domain = (
            bridge_cfg.hyperliquid_domain if bridge_cfg.hyperliquid_domain is not None else 19
        )
        self._mainnet_domain = (
            bridge_cfg.mainnet_domain if bridge_cfg.mainnet_domain is not None else 0
        )
        self._cctp_finality_threshold = bridge_cfg.cctp_finality_threshold

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------
    def bridge_mainnet_to_hyperliquid(
        self,
        amount: float,
        *,
        max_fee: int | None = None,
        min_finality_threshold: int | None = None,
    ) -> BridgeResponse:
        try:
            source_contract = self._connections.ensure_bridge_contract("mainnet")
            destination_contract = self._connections.ensure_bridge_contract("hyper")
        except (ValidationError, NetworkError) as exc:
            return BridgeResponse(
                success=False,
                error=str(exc),
                raw_response={
                    "direction": "mainnet_to_hyper",
                    "field": getattr(exc, "field", None),
                    "value": getattr(exc, "value", None),
                    "details": getattr(exc, "details", None),
                },
            )

        return self._bridge_via_cctp(
            amount=amount,
            source_contract=source_contract,
            destination_contract=destination_contract,
            source_domain=self._mainnet_domain,
            destination_domain=self._hyper_domain,
            direction="mainnet_to_hyper",
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
    ) -> BridgeResponse:
        try:
            source_contract = self._connections.ensure_bridge_contract("hyper")
            destination_contract = self._connections.ensure_bridge_contract("mainnet")
        except (ValidationError, NetworkError) as exc:
            return BridgeResponse(
                success=False,
                error=str(exc),
                raw_response={
                    "direction": "hyper_to_mainnet",
                    "field": getattr(exc, "field", None),
                    "value": getattr(exc, "value", None),
                    "details": getattr(exc, "details", None),
                },
            )

        return self._bridge_via_cctp(
            amount=amount,
            source_contract=source_contract,
            destination_contract=destination_contract,
            source_domain=self._hyper_domain,
            destination_domain=self._mainnet_domain,
            direction="hyper_to_mainnet",
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
        direction: str,
        max_fee_override: int | None,
        min_finality_threshold: int | None,
        source_web3,
        destination_web3,
    ) -> BridgeResponse:
        raw_context: dict[str, Any] = {
            "direction": direction,
            "source_domain": source_domain,
            "destination_domain": destination_domain,
        }

        try:
            amount_units, amount_decimal, truncated = self._normalise_usdc_amount(amount)
        except ValidationError as exc:
            return self._bridge_failure(
                direction=direction,
                error=str(exc),
                amount=None,
                raw=self._with_context(
                    raw_context,
                    field=exc.field,
                    value=exc.value,
                    details=exc.details,
                ),
            )

        if truncated:
            logger.warning(
                "Truncating bridge amount to 6 decimals (%s request on %s)", amount, direction
            )

        amount_float = float(amount_decimal)
        raw_context["amount_units"] = amount_units
        self._stage(direction, "prepare amount", amount=f"{amount_float:.6f}", units=amount_units)

        if max_fee_override is not None and max_fee_override < 0:
            return self._bridge_failure(
                direction=direction,
                error="max_fee must be non-negative",
                amount=amount_float,
                raw=self._with_context(raw_context, max_fee=max_fee_override),
            )

        finality_threshold = (
            min_finality_threshold
            if min_finality_threshold is not None
            else self._cctp_finality_threshold
        )
        raw_context["finality_threshold"] = finality_threshold
        if finality_threshold <= 0:
            return self._bridge_failure(
                direction=direction,
                error="Finality threshold must be positive",
                amount=amount_float,
                raw=raw_context,
            )

        self._stage(direction, "fetch fee quote", source=source_domain, dest=destination_domain)
        try:
            max_fee = (
                max_fee_override
                if max_fee_override is not None
                else self._fetch_cctp_fee(amount_units, source_domain, destination_domain)
            )
        except ValidationError as exc:
            return self._bridge_failure(
                direction=direction,
                error=str(exc),
                amount=amount_float,
                raw=self._with_context(
                    raw_context,
                    field=exc.field,
                    value=exc.value,
                    details=exc.details,
                ),
            )
        except requests.RequestException as exc:
            logger.error("Failed to fetch CCTP fee quote: %s", exc)
            return self._bridge_failure(
                direction=direction,
                error=f"Failed to fetch CCTP fee quote: {exc}",
                amount=amount_float,
                raw=raw_context,
            )

        raw_context["max_fee"] = max_fee
        if max_fee >= amount_units:
            return self._bridge_failure(
                direction=direction,
                error="Quoted max fee exceeds or equals bridge amount",
                amount=amount_float,
                raw=raw_context,
            )

        payload = [VerificationPayload.default().as_tuple()] * 2
        self._stage(direction, "submit burn transaction")
        try:
            burn_tx = source_contract.functions.bridgeUSDCViaCCTPv2(
                amount_units,
                max_fee,
                finality_threshold,
                payload,
            ).transact()
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to submit CCTP burn on %s", direction)
            return self._bridge_failure(
                direction=direction,
                error=str(exc),
                amount=amount_float,
                raw=raw_context,
            )

        burn_tx_hash = burn_tx.to_0x_hex()
        self._stage(direction, "burn submitted", tx=burn_tx_hash)
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
            return self._bridge_failure(
                direction=direction,
                error=str(exc),
                amount=amount_float,
                burn_tx_hash=burn_tx_hash,
                raw=raw_context,
            )
        except ValidationError as exc:
            logger.error("IRIS attestation failed for %s: %s", direction, exc)
            return self._bridge_failure(
                direction=direction,
                error=str(exc),
                amount=amount_float,
                burn_tx_hash=burn_tx_hash,
                raw=self._with_context(
                    raw_context,
                    field=exc.field,
                    value=exc.value,
                    details=exc.details,
                ),
            )

        self._stage(direction, "submit claim transaction")
        try:
            claim_tx = destination_contract.functions.receiveUSDCViaCCTPv2(
                message, attestation
            ).transact()
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to submit CCTP claim on %s", direction)
            return self._bridge_failure(
                direction=direction,
                error=str(exc),
                amount=amount_float,
                burn_tx_hash=burn_tx_hash,
                message=message,
                attestation=attestation,
                raw=raw_context,
            )

        claim_tx_hash = claim_tx.to_0x_hex()
        self._stage(direction, "claim submitted", tx=claim_tx_hash)
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

        self._stage(direction, "bridge complete", burn_tx=burn_tx_hash, claim_tx=claim_tx_hash)
        return self._bridge_success(
            direction=direction,
            amount=float(Decimal(amount_units) / USDC_SCALING),
            burn_tx_hash=burn_tx_hash,
            claim_tx_hash=claim_tx_hash,
            message=message,
            attestation=attestation,
            raw=raw_context,
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

    def _fetch_cctp_fee(self, amount_units: int, src_domain: int, dest_domain: int) -> int:
        url = f"{self._iris_base_url}/v2/burn/USDC/fees/{src_domain}/{dest_domain}"
        logger.info("Fetching CCTP fee quote from IRIS: %s", url)
        response = self._session.get(url, timeout=self._config.request_timeout)
        response.raise_for_status()
        payload = response.json()

        if not isinstance(payload, list):
            raise ValidationError(
                "Unexpected fee response format",
                field="iris_response",
                value=payload,
            )

        entries = [entry for entry in payload if isinstance(entry, Mapping)]
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

    def _poll_iris_attestation(self, direction: str, domain: int, tx_hash: str) -> tuple[str, str]:
        url = f"{self._iris_base_url}/v2/messages/{domain}?transactionHash={tx_hash}"
        self._stage(
            direction,
            "poll IRIS",
            domain=domain,
            tx=tx_hash,
            max_polls=self._iris_max_polls,
            interval=self._iris_poll_interval,
        )

        for attempt in range(self._iris_max_polls):
            try:
                response = self._session.get(url, timeout=self._config.request_timeout)
            except requests.RequestException as exc:  # pragma: no cover - network flake
                logger.debug("IRIS poll error (attempt %s/%s): %s", attempt + 1, self._iris_max_polls, exc)
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
            payload = response.json()
            messages = self._extract_iris_messages(payload)
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

    def _extract_iris_messages(self, payload: Any) -> list[Mapping[str, Any]]:
        if isinstance(payload, Mapping):
            direct = payload.get("messages")
            if isinstance(direct, list):
                return [entry for entry in direct if isinstance(entry, Mapping)]
            data = payload.get("data")
            if isinstance(data, Mapping):
                nested = data.get("messages")
                if isinstance(nested, list):
                    return [entry for entry in nested if isinstance(entry, Mapping)]
        return []

    @staticmethod
    def _with_context(base: Mapping[str, Any], **updates: Any) -> dict[str, Any]:
        context = dict(base)
        context.update({k: v for k, v in updates.items() if v is not None})
        return context

    def _stage(self, direction: str, message: str, **details: Any) -> None:
        suffix = ""
        if details:
            formatted = ", ".join(f"{key}={value}" for key, value in details.items())
            suffix = f" ({formatted})"
        logger.info("Stage CCTP [%s]: %s%s", direction, message, suffix)

    def _bridge_failure(
        self,
        *,
        direction: str,
        error: str,
        amount: float | None,
        raw: Mapping[str, Any],
        burn_tx_hash: str | None = None,
        message: str | None = None,
        attestation: str | None = None,
    ) -> BridgeResponse:
        self._stage(direction, "bridge aborted", reason=error)
        context = dict(raw)
        return BridgeResponse(
            success=False,
            amount=amount,
            burn_tx_hash=burn_tx_hash,
            claim_tx_hash=None,
            message=message,
            attestation=attestation,
            error=error,
            raw_response=context,
        )

    def _bridge_success(
        self,
        *,
        direction: str,
        amount: float,
        burn_tx_hash: str,
        claim_tx_hash: str,
        message: str,
        attestation: str,
        raw: Mapping[str, Any],
    ) -> BridgeResponse:
        context = dict(raw)
        return BridgeResponse(
            success=True,
            amount=amount,
            burn_tx_hash=burn_tx_hash,
            claim_tx_hash=claim_tx_hash,
            message=message,
            attestation=attestation,
            raw_response=context,
        )
