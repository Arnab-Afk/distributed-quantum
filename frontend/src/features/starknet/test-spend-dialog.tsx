"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { useStarknetWallet } from "./use-starknet-wallet";
import { useNoteStarknetTx, useSpendStarknetSession } from "@/features/agentkit/hooks/use-agents";
import { Loader2 } from "lucide-react";

export function TestSpendDialog({
  agentId,
  open,
  onOpenChange,
}: {
  agentId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [amount, setAmount] = useState("1");
  const [walletPicker, setWalletPicker] = useState(false);
  const [step, setStep] = useState<"config" | "connecting" | "signing">("config");

  const { address, connectWallet, signAndSend, isConnecting } = useStarknetWallet();
  const spendSession = useSpendStarknetSession();
  const noteTx = useNoteStarknetTx();

  useEffect(() => {
    if (!walletPicker) return;
    let active = true;
    const timer = window.setTimeout(() => {
      document.body.style.pointerEvents = "auto";
      connectWallet()
        .then(() => {
          if (active) setStep("config");
        })
        .finally(() => {
          document.body.style.pointerEvents = "";
          if (active) setWalletPicker(false);
        });
    }, 150);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [walletPicker, connectWallet]);

  const handleSpend = async () => {
    if (!address) {
      setStep("connecting");
      setWalletPicker(true);
      return;
    }

    setStep("signing");
    try {
      const { spend } = await spendSession.mutateAsync({ agentId, amount });

      toast.info("Sign spend in your wallet");
      const txHash = await signAndSend(spend.contract, spend.entrypoint, spend.calldata);

      try {
        await noteTx.mutateAsync({ agentId, kind: "spend", txHash, amount });
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : "Could not save the transaction hash";
        toast.error(message);
      }
      toast.success(`Spent ${amount} STRK`, {
        description: `${txHash.slice(0, 8)}…${txHash.slice(-4)}`,
      });
      onOpenChange(false);
      setStep("config");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Spend failed";
      toast.error(message);
      setStep("config");
    }
  };

  return (
    <Dialog open={open && !walletPicker} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Test Spend</DialogTitle>
          <DialogDescription>
            Preflight checks caps. Owner signs spend on the contract.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label htmlFor="amount">Amount (STRK)</Label>
            <Input
              id="amount"
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              disabled={step !== "config"}
            />
          </div>

          <Button
            onClick={handleSpend}
            disabled={isConnecting || spendSession.isPending || step !== "config"}
            className="w-full"
          >
            {step === "connecting" || isConnecting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Connecting wallet...
              </>
            ) : step === "signing" || spendSession.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Signing spend...
              </>
            ) : address ? (
              "Test Spend"
            ) : (
              "Connect Ready Wallet"
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
