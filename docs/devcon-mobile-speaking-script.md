# DevCon demo — phone speaking script

About 3–4 minutes. Read the **Say** passages aloud. **Type** passages go into the agent chat on your computer. Everything else is a stage direction.

## Before recording

- Keep your computer awake and both local servers running.
- Open [Toju health](https://toju-devcon-testnet.onrender.com/health) on your computer. Wait for it to report healthy; the free server may need time to wake.
- Open [QuantumNodes chat](http://localhost:3000/agents/chat) on your computer and start a fresh conversation. Sign in if prompted.
- Keep this script on your phone. The localhost links work on the computer running the app, not on your phone.
- Keep API keys, email and provider dashboards outside the recording.

## 1. Introduce the demo

**Show:** The agent chat.

**Say:**

“This is QuantumNodes, our distributed quantum research platform. Today I’m showing how a research agent can save its work through Toju, with my approval before anything is published or paid for.”

## 2. Ask for a research draft

**Type:**

> Draft a short Bell-pair experiment proposal, under 100 words. Include the goal, circuit steps and expected observations. Clearly label it as a proposed experiment that has not been run. Show only the draft for now.

**Say while it responds:**

“I’m asking the agent for an experiment proposal. We haven’t run this experiment, so the draft must distinguish expected observations from actual results.”

**Do:** Wait for the complete response. Briefly show the proposal.

## 3. Ask naturally to save it

**Type:**

> Let's store this proposal so we can access it later.

**Say:**

“I can ask to save it in ordinary language. I don’t need to name an API or a storage tool.”

**Do:** Wait for the storage approval card. If the agent already created a card for this exact draft in the previous step, go directly to reviewing it instead of requesting another.

## 4. Review before approving

**Click:** **Review exact content and payment recipient**.

**Say:**

“The agent has prepared a storage request. It hasn’t published the file yet. I can review the exact text, content hash, recipient, retention period and testnet price.”

“The card also tells me that IPFS content is public. I can approve this specific file or cancel.”

**Do:** Check that the text matches your draft and the payment network says **Base Sepolia**. Read the price shown on the card; do not assume every draft has the same price.

## 5. Approve once

**Click:** **Approve & store** once.

**Say:**

“I’m approving this artifact. The backend checks the request and uses faucet USDC on Base Sepolia. No real money is involved.”

**Do:** Wait. Continue to the next section only when the card says **Stored and retrieved. SHA-256 verified.**

## 6. Show the evidence

**Say after the verified label appears:**

“Toju has stored the report. Our app has checked the testnet payment and retrieved the file to verify that its content matches what I approved.”

**Click:** **Open stored artifact**.

**Say:**

“Here is the saved report, accessible through its IPFS link.”

**Do:** Return to the chat, then click **View testnet payment**.

**Say:**

“And here is the corresponding payment on Base Sepolia.”

## 7. Show persistence and finish

**Do:** Return to chat and reload the page. Show the stored receipt beside the original response.

**Say:**

“The conversation and receipt remain available after a reload. The storage card stays with the response it belongs to, and later messages continue underneath.”

“This connects the research conversation to a saved, verifiable artifact, while keeping publication and payment under the user’s control.”

## Optional: show the next message

Skip this to conserve model quota. If you include it, do it before the closing sentence.

**Type:**

> In one sentence, summarize what we just saved.

**Do:** Show the new response below the storage card.

## If someone asks about the deployment

**Say:**

“The full Toju server runs separately on Render, with Neon for its database and signed QStash jobs. QuantumNodes is running locally for this recording. This agent storage flow pays on Base Sepolia. The server’s Solana configuration uses Solana testnet.”

## If something interrupts the recording

- **Model rate limit:** Stop the take and wait for the displayed reset. Do not repeatedly resubmit.
- **Uncertain payment or receipt:** Click **Check receipt (no new payment)**. Do not approve another export to recover the same attempt.
- **Still no verified receipt:** Stop the take. Do not describe that attempt as successful.
- **Approval expired:** Do not use that old card for the recording. Start with a fresh draft when ready.

For a walkthrough of a previously completed test, open the [verified sample chat](http://localhost:3000/agents/chat?sessionId=2bddbf60-5dab-4023-b513-f614ced3185b) and say: “This is a previously verified test export.” Its history also contains a later unsettled attempt; show the verified **DevCon Demo** card specifically.

## Rehearsal notes — do not read aloud

The natural save wording is supported by the agent’s existing tool instructions. This exact two-message script has not been run live, to preserve your model quota. One earlier export was verified end to end; the newer final-check draft was still awaiting approval when this script was prepared. Free-service quotas, cold starts and settlement failures can interrupt a take.

This demo saves a proposal. It does not demonstrate an executed quantum experiment or a Solana payment.
