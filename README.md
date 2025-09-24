# HyperLiquid Unified API

|[![CI](https://github.com/Moonsong-Labs/hl-api/actions/workflows/ci.yml/badge.svg)](https://github.com/Moonsong-Labs/hl-api/actions/workflows/ci.yml) |[![E2E](https://github.com/Moonsong-Labs/hl-api/actions/workflows/e2e.yml/badge.svg)](https://github.com/Moonsong-Labs/hl-api/actions/workflows/e2e.yml) |
|---|---|

A unified Python API for interacting with HyperLiquid through both the Core SDK and EVM CoreWriter precompile.

## Usage

### Pre-requisites

Install `uv` via their official [docs](https://docs.astral.sh/uv/#installation). The one-liner is:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

> [!IMPORTANT]  
> `uv` is highly recommended to use, other package managers are untested on this repo.

### Installation

```sh
uv sync
```

## Quick Start

### Using HyperLiquid Core

```python
from hl_api import HLProtocolCore

# Initialize Core protocol
hl = HLProtocolCore(
    private_key="YOUR_PRIVATE_KEY",
    testnet=True,  # Use mainnet in production
)

try:
    # Connect
    hl.connect()

    # Place a limit order
    response = hl.limit_order(
        asset="BTC",  # BTC-PERP
        is_buy=True,
        limit_px=65000.0,  # $65,000
        sz=0.1,  # 0.1 BTC
        tif="GTC",
    )

    if response.success:
        print(f"Order placed: {response.order_id}")
finally:
    # Disconnect
    hl.disconnect()
```

### Using HyperLiquid EVM

The EVM connector routes CoreWriter actions through a deployed
`HyperliquidStrategy` contract and is intended for vault integrations.
Provide the strategy address during construction.

```python
import os

from hl_api import HLProtocolEVM


hl = HLProtocolEVM(
    private_key=os.environ["PRIVATE_KEY"],
    hl_rpc_url = os.getenv("HYPER_EVM_RPC", "https://rpc.hyperliquid-testnet.xyz/evm")
    mn_rpc_url = os.getenv("HL_EVM_RPC", "https://sepolia.drpc.org"),
    hl_strategy_address=os.environ["HYPERLIQUID_STRATEGY"],
    bridge_strategy_address=os.environ["HYPERLIQUID_BRIDGE_STRATEGY"],
)


hl.connect()

try:
    response = hl.limit_order(
        asset="BTC",
        is_buy=True,
        limit_px=65000.0,
        sz=0.05,
        tif="GTC",
    )
    print(response)
finally:
    hl.disconnect()
```

Key parameters:

- `hl_strategy_address` (required) – deployed `HyperliquidStrategy` contract on HyperLiquid EVM.
- `bridge_strategy_address` (required) – contract used for bridging to mainnet when needed by strategy flows.
  `{action}` is substituted with the method name.

> [!NOTE]
> Some CoreWriter actions (delegation, staking, builder fees, direct vault
> transfers) are not currently implemented by the vault strategy and will
> return a failure response from the connector.

## Testing Setup

### Prerequisites

To test with HyperLiquid Testnet, you need a funded account. The testnet faucet requires at least 0.1 USDC in the same address on mainnet.

### Mainnet Setup (Required for Testnet Access)

1. **Add Networks**: Add both mainnet and testnet to your wallet using [Chainlist](https://chainlist.org/?chain=999&search=hyper&testnets=true)

2. **Fund Arbitrum Account**: Get USDC (≥5) and ETH (≥0.01) on Arbitrum

3. **Enable Trading**:
   - Connect to [HyperLiquid mainnet](https://app.hyperliquid.xyz/trade)
   - Deposit 5 USDC from Arbitrum using "Enable trading"

### Testnet Setup

1. **Access Faucet**: Visit [testnet faucet](https://app.hyperliquid-testnet.xyz/drip)
2. **Switch Networks**: Connect to HyperEVM Testnet with the same address
3. **Claim Tokens**: Click "claim mock USDC" to receive 999 USD

### Environment Configuration

Create a `.env` file:

```env
PRIVATE_KEY=your_private_key_here
ACCOUNT_ADDRESS=your_account_address
```

### Run Example

```bash
uv run examples/01_place_and_cancel_order.py
```

Expected output:

```bash
==================================================
HyperLiquid API - Example 01
📈 Place & Cancel Limit Orders
==================================================
Order placed successfully!
Order ID: 39205192325
Client Order ID: 0x767f340108a94fbab418d5f6b2fd5ff5
Order cancelled successfully!
```

```bash
uv run examples/08_evm_cctp_roundtrip.py  
```

Expected output:

```bash
2025-09-23 15:56:02,149 INFO hl_api.evm.connections: Connected to HyperLiquid RPC at https://rpc.hyperliquid-testnet.xyz/evm
2025-09-23 15:56:02,149 INFO hl_api.evm.connections: Connected to mainnet RPC at https://sepolia.drpc.org
2025-09-23 15:56:02,149 INFO cctp_roundtrip: Bridging 10.000000 USDC from mainnet to HyperEVM
2025-09-23 15:56:02,380 INFO hl_api.evm.bridge: CCTP fee quote 0 -> 19: bps=1 maxFee=1000
2025-09-23 15:56:47,439 INFO cctp_roundtrip: Mainnet -> HyperEVM succeeded (amount 10.000000 USDC)
2025-09-23 15:56:47,439 INFO cctp_roundtrip:   burn tx: 0xef00e08df0b0147f16521ccc3d9d6f032c6fc144c23c7741a232cc48c8fd7e4c
2025-09-23 15:56:47,439 INFO cctp_roundtrip:   claim tx: 0x05d227283a41dd0313c43db4dd7c8156d3e013367bccda2642d22a60ed6a77c9
2025-09-23 15:56:47,440 INFO cctp_roundtrip: Bridging 10.000000 USDC from HyperEVM back to mainnet
2025-09-23 15:56:47,598 INFO hl_api.evm.bridge: CCTP fee quote 19 -> 0: bps=0 maxFee=0
2025-09-23 15:57:00,477 INFO cctp_roundtrip: HyperEVM -> Mainnet succeeded (amount 10.000000 USDC)
2025-09-23 15:57:00,477 INFO cctp_roundtrip:   burn tx: 0xfd3eb0b2ee1f189603de4910de52f44c03d82202576463b770b5b013cd801795
2025-09-23 15:57:00,477 INFO cctp_roundtrip:   claim tx: 0x26e8b84afc0a8015a6a8060ccff05d6c4a28b94d5d6cd14b9096c9589e47bf0f
2025-09-23 15:57:00,477 INFO cctp_roundtrip: Disconnected
```

## Supported Operations

All operations correspond to CoreWriter precompile actions:

| Method | Action ID | Description |
|--------|-----------|-------------|
| `limit_order` | 1 | Place a limit order |
| `vault_transfer` | 2 | Transfer to/from vault |
| `token_delegate` | 3 | Delegate/undelegate tokens |
| `staking_deposit` | 4 | Deposit for staking |
| `staking_withdraw` | 5 | Withdraw from staking |
| `spot_send` | 6 | Send spot tokens |
| `perp_send` | 7 | Send perp collateral |
| `usd_class_transfer_to_perp` | 8 | Transfer USD to perp |
| `usd_class_transfer_to_spot` | 9 | Transfer USD to spot |
| `cancel_order` | 10 | Cancel order by cloid |
| `finalize_subaccount` | 11 | Finalize subaccount |
| `approve_builder_fee` | 12 | Approve builder fee |

## Integration

### Place & cancel a limit order

```python
cloid = generate_cloid()
hl.limit_order(
    asset="BTC",
    is_buy=True,
    limit_px=60000.0,
    sz=0.001,
    tif="GTC",
    cloid=cloid,
)
hl.cancel_order(asset="BTC", order_id=cloid)
```

Args:

- `asset` – symbol to quote; e.g. `BTC`, `ETH`. Perp symbol from [trading docs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals#retrieve-perpetuals-metadata-universe-and-margin-tables)
- `is_buy` – `True` to bid, `False` to ask
- `limit_px` – limit price in USD
- `sz` – base asset size
- `tif` – time-in-force (`"GTC"`, `"IOC"`, etc.)
- `cloid` – optional client order ID reused for cancellation

### Fetch market prices

```python
price = hl.get_market_price("BTC")
```

Args:

- `asset` – symbol to quote; e.g. `BTC`, `ETH`. Perp symbol from [trading docs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals#retrieve-perpetuals-metadata-universe-and-margin-tables)

### Submit market & close orders

```python
cloid = generate_cloid()
hl.market_order(asset="BTC", is_buy=True, sz=0.0001, slippage=0.005, cloid=cloid)
hl.market_close_position(asset="BTC", size=None, slippage=0.02, cloid=generate_cloid())
```

Args:

- `asset` – symbol to quote; e.g. `BTC`, `ETH`. Perp symbol from [trading docs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals#retrieve-perpetuals-metadata-universe-and-margin-tables)
- `is_buy` – direction flag; ignored for `market_close_position`
- `sz` – quantity filled immediately at market
- `slippage` – max price impact (e.g. `0.005` = 0.5%)
- `cloid` – client order identifier per request
- `size` – position size to flatten; `None` closes all

### USD class transfers

```python
hl.usd_class_transfer_to_spot(0.23)
hl.usd_class_transfer_to_perp(0.2)
```

Args:

- `amount` – USD to move between perp and spot vaults; see [portfolio docs](https://docs.hyperliquid.xyz/core/portfolio)