# HyperLiquid Unified API

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
Provide the strategy address during construction and optionally point the
client at JSON resources for metadata and verification payloads.

```python
import os

from hl_api import HLProtocolEVM

hl = HLProtocolEVM(
    private_key=os.environ["PRIVATE_KEY"],
    rpc_url=os.environ.get("HYPER_EVM_RPC", "https://rpc.hyperliquid.xyz"),
    strategy_address=os.environ["HYPERLIQUID_STRATEGY"],
    verification_payload_url=os.environ.get("HYPERLIQUID_VERIFICATION_URL"),
)

hl.connect()
hl.load_asset_metadata_from_info()
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

- `strategy_address` (required) – deployed `HyperliquidStrategy` contract.
- `load_asset_metadata_from_url(url)` (optional) – populate symbol/token indices after construction.
- `verification_payload_url` (optional) – URL template returning verification payload JSON;
  `{action}` is substituted with the method name.
- `verification_payload_resolver` (optional) – Python callable to generate custom payloads.

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

```sh
==================================================
HyperLiquid API - Example 01
📈 Place & Cancel Limit Orders
==================================================
Order placed successfully!
Order ID: 39205192325
Client Order ID: 0x767f340108a94fbab418d5f6b2fd5ff5
Order cancelled successfully!
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

## Error Handling

```python
from hl_api import (
    HLProtocolError,
    OrderError,
    ValidationError
)

try:
    response = hl.limit_order(...)
except ValidationError as e:
    print(f"Invalid input: {e.message}")
    print(f"Field: {e.field}, Value: {e.value}")
except OrderError as e:
    print(f"Order failed: {e.message}")
except HLProtocolError as e:
    print(f"Protocol error: {e.message}")
```

## Examples

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

## Architecture

```sh
HLProtocolBase (Abstract)
    ├── HLProtocolCore (HyperLiquid SDK implementation)
    └── HLProtocolEVM (CoreWriter precompile implementation)
```

### API

> [!NOTE]  
> This useful for when you want to check via the REST API certain values, consult the docs for [INFO](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint) and [EXCHANGE](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint) endpoints. This is not a replacement for this API lib, but can be used for manual inspection of values.

#### Get all Mids

```sh
curl --location 'https://api.hyperliquid-testnet.xyz/info' \
--header 'Content-Type: application/json' \
--data '{
    "type": "allMids",
    "dex": ""
}'
```

#### Get User Balance

```sh
curl --location 'https://api.hyperliquid-testnet.xyz/info' \
--header 'Content-Type: application/json' \
--data '{
    "type": "spotClearinghouseState",
    "user":"0xb764428a29EAEbe8e2301F5924746F818b331F5A"
}'
```

#### Get Perp Info

```sh
curl --location 'https://api.hyperliquid-testnet.xyz/info' \
--header 'Content-Type: application/json' \
--data '{
    "type": "metaAndAssetCtxs"
}'
```

#### Get Orderbook snapshot

```sh
curl --location 'https://api.hyperliquid-testnet.xyz/info' \
--header 'Content-Type: application/json' \
--data '{
    "type": "l2Book",
    "coin": "FARTCOIN"
}'
```
