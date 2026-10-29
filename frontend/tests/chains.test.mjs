import { expect, test } from "bun:test";
import { explorerUrl, findChain, supports } from "../src/features/chains/lib/chains";

const registry = {
  default_chain_id: "eip155:84532",
  chains: [
    {
      chain_id: "eip155:84532",
      family: "evm",
      display_name: "Base Sepolia",
      aliases: ["base-sepolia"],
      testnet: true,
      native_token: { symbol: "ETH", decimals: 18 },
      stablecoin: { symbol: "USDC", decimals: 6, address: "0x036CbD53842c5426634e7929541eC2318f3dCF7e" },
      explorers: {
        transaction: "https://sepolia.basescan.org/tx/{tx_hash}",
        address: "https://sepolia.basescan.org/address/{address}",
        block: "https://sepolia.basescan.org/block/{block_number}",
      },
      capabilities: ["explorer_url", "create_wallet", "transfer_stablecoin", "aave_supply"],
    },
    {
      chain_id: "eip155:11155111",
      family: "evm",
      display_name: "Ethereum Sepolia",
      aliases: ["ethereum-sepolia"],
      testnet: true,
      native_token: { symbol: "ETH", decimals: 18 },
      stablecoin: null,
      explorers: {
        transaction: "https://sepolia.etherscan.io/tx/{tx_hash}",
        address: "https://sepolia.etherscan.io/address/{address}",
        block: "https://sepolia.etherscan.io/block/{block_number}",
      },
      capabilities: ["explorer_url", "verify_transaction"],
    },
  ],
};

test("chains resolve by CAIP-2 id or by the legacy alias stored on wallets", () => {
  expect(findChain(registry, "eip155:84532")?.display_name).toBe("Base Sepolia");
  expect(findChain(registry, "base-sepolia")?.chain_id).toBe("eip155:84532");
  expect(findChain(registry, "ethereum-sepolia")?.chain_id).toBe("eip155:11155111");
});

test("unknown, empty or missing networks never fall back to the default", () => {
  expect(findChain(registry, "base-mainnet")).toBeUndefined();
  expect(findChain(registry, "")).toBeUndefined();
  expect(findChain(registry, null)).toBeUndefined();
  expect(findChain(undefined, "base-sepolia")).toBeUndefined();
});

test("explorer links fill the template's terminal placeholder", () => {
  const base = registry.chains[0];
  expect(explorerUrl(base, "transaction", "0xabc")).toBe("https://sepolia.basescan.org/tx/0xabc");
  expect(explorerUrl(base, "address", "0xdef")).toBe("https://sepolia.basescan.org/address/0xdef");
  expect(explorerUrl(base, "block", "42")).toBe("https://sepolia.basescan.org/block/42");
  expect(explorerUrl(base, "transaction", "a/b?c")).toBe("https://sepolia.basescan.org/tx/a%2Fb%3Fc");
});

test("capabilities gate which operations a chain offers", () => {
  expect(supports(registry.chains[0], "aave_supply")).toBe(true);
  expect(supports(registry.chains[1], "transfer_stablecoin")).toBe(false);
});
