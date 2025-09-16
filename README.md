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

> [!IMPORTANT]  
> This is pending `flexible-vault` & `strategy` contract deployment and is not yet ready for use.

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

### Placing Limit Order

### Canceling Order

### Modifying Order

## Architecture

```sh
HLProtocolBase (Abstract)
    ├── HLProtocolCore (HyperLiquid SDK implementation)
    └── HLProtocolEVM (CoreWriter precompile implementation)
```
