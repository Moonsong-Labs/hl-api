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
import asyncio
from hl_api import HLProtocolCore, price_to_uint64, size_to_uint64

async def main():
    # Initialize Core protocol
    hl = HLProtocolCore(
        private_key="YOUR_PRIVATE_KEY",
        testnet=True  # Use mainnet in production
    )
    
    # Connect
    await hl.connect()
    
    # Place a limit order
    response = await hl.limit_order(
        asset="BTC",  # BTC-PERP
        is_buy=True,
        limit_px=price_to_uint64(65000),  # $65,000
        sz=size_to_uint64(0.1),           # 0.1 BTC
        tif="GTC"
    )
    
    if response.success:
        print(f"Order placed: {response.order_id}")
    
    # Disconnect
    await hl.disconnect()

asyncio.run(main())
```

### Using HyperLiquid EVM

> [!IMPORTANT]  
> This is pending `flexible-vault` & `strategy` contract deployment and is not yet ready for use.

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

## Type Conversions

The API handles uint64 conversions internally:

```python
from hl_api import price_to_uint64, size_to_uint64

# Convert human-readable values to uint64
price = price_to_uint64(65000)     # $65,000 -> uint64
size = size_to_uint64(0.1)         # 0.1 BTC -> uint64

# Generate client order IDs
from hl_api import generate_cloid
cloid = generate_cloid()  # Random uint128
```

## Error Handling

```python
from hl_api import (
    HLProtocolError,
    OrderError,
    ValidationError
)

try:
    response = await hl.limit_order(...)
except ValidationError as e:
    print(f"Invalid input: {e.message}")
    print(f"Field: {e.field}, Value: {e.value}")
except OrderError as e:
    print(f"Order failed: {e.message}")
except HLProtocolError as e:
    print(f"Protocol error: {e.message}")
```

## Examples

### Placing Limit Order

### Canceling Order

### Modifying Order

## Architecture

```sh
HLProtocolBase (Abstract)
    ├── HLProtocolCore (HyperLiquid SDK implementation)
    └── HLProtocolEVM (CoreWriter precompile implementation)
```
