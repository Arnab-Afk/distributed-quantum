import { EXTERNAL_LINKS, ROUTES } from "@/constants";


export const REPOSITORY_URL = EXTERNAL_LINKS.REPOSITORY;
export const RESEARCH_URL = EXTERNAL_LINKS.RESEARCH_PAPER;
export const DEMO_URL = EXTERNAL_LINKS.DEMO_VIDEO;
const DOCS = EXTERNAL_LINKS.DOCS;
export const CONSOLE_HREF = `${ROUTES.SIGNIN}?next=${ROUTES.DASHBOARD}`;

export const NAV = {
  links: [
    { label: "Architecture", href: "#architecture" },
    { label: "Workloads", href: "#workloads" },
    { label: "Results", href: "#results" },
    { label: "Developers", href: "#developers" },
    { label: "Team", href: "#team" },
  ],
  secondary: "GitHub",
  primary: "Open the console",
} as const;

export const HERO = {
  title: ["Quantum, run", "as a network"],
  body: "Split quantum circuits across a peer-to-peer mesh of ordinary devices, pay each peer per request, and get a receipt for every result.",
  muted: "Simulated qubits on real network infrastructure.",
  primary: "Watch the demo",
  secondary: "Open the console",
  ribbon: "Runs on anything that runs Python",
  sceneCaption: "Six spare devices across the world, one machine · illustrative locations, simulated qubits",
  scene:
    "Isometric world map with six floating peers pinned over San Francisco, São Paulo, Cape Town, London, Mumbai and Tokyo: a laptop, an old phone, a Raspberry Pi cluster, an old CRT desktop, a Raspberry Pi and a mini PC, linked by arcs over the map. Circuit fragments arc down from one large qubit sphere to each peer, a small qubit above each one evolves and is measured, and the bits arc back up into the sphere: the mesh acting as one machine, with a receipt for the result.",
} as const;

export const GLYPHS = {
  label: "A drifting field of 0 and 1 characters in diagonal bands; moving the pointer brightens a short trail.",
} as const;

export const BUILT_ON = {
  label: "Infrastructure behind QMesh",
  short: "Built on",
  pause: "Pause motion",
  resume: "Resume motion",
  rowLabels: ["Network and execution", "Services and integrations"],
  rows: [
    [
      { name: "py-libp2p", role: "Peer networking" },
      { name: "Qiskit", role: "Quantum simulation" },
      { name: "PennyLane", role: "Quantum workflows" },
      { name: "IPFS", role: "Content addressing" },
      { name: "Helia", role: "Browser vault" },
      { name: "Kubo", role: "Platform content node" },
      { name: "Algorand x402", role: "Per-request payments" },
      { name: "Ethereum Sepolia", role: "Provenance anchoring" },
      { name: "Base Sepolia", role: "Wallet transactions" },
      { name: "Starknet Sepolia", role: "Spending policies" },
    ],
    [
      { name: "Chainlink", role: "Verifiable price feeds" },
      { name: "Robinhood Chain", role: "Tokenized stock data" },
      { name: "ENS", role: "Name resolution" },
      { name: "Coinbase CDP", role: "Agent wallets" },
      { name: "Stripe", role: "Subscriptions and credits" },
      { name: "NEAR AI Cloud", role: "Private inference" },
      { name: "Groq", role: "Agent inference" },
      { name: "OpenRouter", role: "Model routing" },
      { name: "Lighthouse", role: "Vault pinning" },
      { name: "Toju", role: "Approved storage exports" },
    ],
  ],
} as const;

export interface Layer {
  key: "app" | "coordinator" | "payments" | "mesh" | "provenance";
  name: string;
  title: string;
  body: string;
  /** One label per component on the plate, in the order the plate draws its anchors. */
  callouts: readonly string[];
}

export const ARCHITECTURE: { title: [string, string]; body: string; layers: ReadonlyArray<Layer> } = {
  title: ["Quantum infrastructure built in", "layers"],
  body: "One coordinator, a mesh of ordinary devices, a payment per request and a receipt for every result.",
  layers: [
    {
      key: "app",
      name: "Your app",
      title: "Submit",
      body: "Send OpenQASM from the console or the API, and get a receipt back.",
      callouts: ["Operator console", "Job status", "OpenQASM editor", "REST API"],
    },
    {
      key: "coordinator",
      name: "Coordinator",
      title: "Plan",
      body: "The coordinator turns each circuit into a distributed execution plan.",
      callouts: ["Coordinator", "Execution plan", "Circuit fragments", "Peer reservation"],
    },
    {
      key: "payments",
      name: "Payments and registry",
      title: "Pay",
      body: "Every run pays its peers per request, in Algorand USDC on TestNet.",
      callouts: ["USDC on Algorand", "x402 receipt", "Chain registry"],
    },
    {
      key: "mesh",
      name: "Peer mesh",
      title: "Run",
      body: "Worker peers on py-libp2p run their fragments with Qiskit.",
      callouts: ["Laptop", "Raspberry Pi", "Old desktop", "Old phone", "Mini PC", "libp2p links"],
    },
    {
      key: "provenance",
      name: "Provenance",
      title: "Prove",
      body: "Every result becomes a provenance bundle, pinned on IPFS by content.",
      callouts: ["Merkle root", "Branch hashes", "Result bundles", "Pinned by CID"],
    },
  ],
};

export interface Workload {
  title: string;
  body: string;
  points: readonly [string, string, string];
  status: "Available" | "In review" | "Experimental";
  href: string;
  action: string;
  card: { label: string; meta: string; headline: string; headlineLabel: string; rows: ReadonlyArray<[string, string]> };
  api: string;
}

export const WORKLOADS: { title: string; items: ReadonlyArray<Workload> } = {
  title: "Designed for real workloads",
  items: [
    {
      title: "Distributed circuits",
      body: "Normalize OpenQASM, plan fragments and execute them across worker peers, with every fallback recorded.",
      points: ["OpenQASM in", "Fragments over libp2p", "Qiskit statevector"],
      status: "Available",
      href: CONSOLE_HREF,
      action: "Run a circuit",
      card: {
        label: "Circuit job",
        meta: "Bell pair · 2 qubits",
        headline: "queued",
        headlineLabel: "Status",
        rows: [
          ["Transport", "py-libp2p"],
          ["Engine", "Qiskit"],
          ["Payment", "x402"],
        ],
      },
      api: `POST /api/x402/quantum/runs
{ "circuit": "OPENQASM 2.0; include \\"qelib1.inc\\"; qreg q[2]; creg c[2]; h q[0]; cx q[0],q[1]; measure q -> c;" }`,
    },
    {
      title: "Portfolio optimization",
      body: "QAOA benchmarked against classical baselines, with every measured state and coupling inspectable.",
      points: ["QAOA vs classical", "Bloch state per asset", "Ising couplings"],
      status: "Available",
      href: RESEARCH_URL,
      action: "Read the benchmark",
      card: {
        label: "Portfolio run",
        meta: "Tokenized stocks",
        headline: "5 qubits",
        headlineLabel: "Circuit",
        rows: [
          ["Depth", "24"],
          ["Gates", "43"],
          ["Baseline", "Classical"],
        ],
      },
      api: `POST /benchmark/portfolio
{ "max_assets": 10, "risk_aversion": 0.5 }`,
    },
    {
      title: "Risk and option pricing",
      body: "VaR, CVaR, credit-risk and option-pricing experiments run beside their classical methods.",
      points: ["VaR and CVaR", "Credit risk", "QAE option pricing over x402"],
      status: "Available",
      href: DOCS.BACKEND,
      action: "Backend docs",
      card: {
        label: "Options run",
        meta: "QAE pipeline",
        headline: "402",
        headlineLabel: "Pay to run",
        rows: [
          ["Route", "/options/runs"],
          ["Settles", "Algorand USDC"],
          ["Network", "TestNet"],
        ],
      },
      api: `POST /api/x402/options/runs
→ 402 Payment Required (Algorand USDC, TestNet)`,
    },
    {
      title: "Provenance anchoring",
      body: "Batches of provenance bundles become one Merkle root in a single Ethereum Sepolia transaction.",
      points: ["Bundles pinned on IPFS", "One root per batch", "Counted once final"],
      status: "In review",
      href: DOCS.PROVENANCE,
      action: "Provenance docs",
      card: {
        label: "Anchor batch",
        meta: "Ethereum Sepolia",
        headline: "≈22.7k",
        headlineLabel: "Gas per batch",
        rows: [
          ["Per batch", "1 tx"],
          ["Counts", "Final only"],
          ["Status", "In review"],
        ],
      },
      api: `provenance bundle → IPFS (CID) → Merkle root → Sepolia tx`,
    },
    {
      title: "Drug-discovery pipeline",
      body: "Molecular filters with simulated quantum stages, for early research only.",
      points: ["Molecular filters", "Simulated quantum stages", "ADMET heuristics"],
      status: "Experimental",
      href: DOCS.OVERVIEW,
      action: "Overview",
      card: {
        label: "Pharma job",
        meta: "Research only",
        headline: "202",
        headlineLabel: "Accepted",
        rows: [
          ["Stages", "Simulated"],
          ["Filters", "Molecular"],
          ["Status", "Experimental"],
        ],
      },
      api: `POST /api/v1/pharma/submit
→ 202 Accepted { "job_id", "status", "submitted_at" }`,
    },
  ],
};

export const PRODUCTS = {
  title: "What's in the repository",
  groups: [
    {
      title: "Platform",
      items: [
        { icon: "console", title: "Operator console", body: "Peers, jobs and quantum analysis, live" },
        { icon: "coordinator", title: "Coordinator API", body: "FastAPI service that plans and routes jobs" },
        { icon: "peer", title: "Worker peers", body: "py-libp2p processes that run fragments" },
        { icon: "registry", title: "Chain registry", body: "Testnet metadata behind one reviewed file" },
      ],
    },
    {
      title: "Trust",
      items: [
        { icon: "payment", title: "x402 payments", body: "Pay per request in Algorand USDC" },
        { icon: "bundle", title: "Provenance bundles", body: "Hashed inputs, plan and results per run" },
      ],
    },
    {
      title: "Research",
      items: [
        { icon: "benchmark", title: "Benchmarks", body: "QAOA against classical, published both ways" },
        { icon: "paper", title: "Research paper", body: "The full analysis behind every number" },
      ],
    },
  ],
} as const;

export const RESULTS = {
  title: "Results you can check",
  action: "Watch the demo",
  /** The scroll story, told like giga.ai's Build → Observe → Improve, with QMesh's own content. */
  story: {
    label:
      "Scroll story. Mesh: strands from laptops, Raspberry Pis and old phones converge into one machine. Run: the machine bursts into a field of fragments that cluster by workload, then line up by workload over time. Scale: they settle on a chart where QAOA on the mesh climbs from parity at 20 assets to 3.2 times faster at 40 and 9.5 times faster at 60.",
    sources: ["Laptops", "Raspberry Pis", "Old phones"],
    point: "One machine",
    pointLoop: "One machine, next run",
    phases: [
      { key: "mesh", title: "Mesh.", body: "Bring spare devices together into one machine." },
      { key: "run", title: "Run.", body: "See every fragment as it runs across the mesh." },
      { key: "scale", title: "Scale.", body: "Where QAOA on the mesh overtakes classical search." },
    ],
    loop: { title: "Every result comes back with a receipt.", body: "The next run begins." },
    rows: ["Circuits", "Portfolios", "Risk & options", "Anchoring", "Pharma"],
    runAxis: ["Earlier", "Recent"],
    runNote: "Illustrative",
    chart: {
      baselineLabel: "Speedup over classical",
      marker: "Classical wins up to 20 assets",
      gain: "Gain",
      current: "Classical",
      points: [
        { assets: 40, speedup: 3.2, label: "3.2× at 40 assets" },
        { assets: 60, speedup: 9.5, label: "9.5× at 60 assets" },
      ],
      note: "Measured at 40 and 60 assets; the curve between is illustrative.",
    },
    action: "Read the paper",
  },
  stats: [
    { value: "97", suffix: "%", title: "Run time in classical search", body: "Most of a QAOA run is COBYLA parameter search, not the circuit." },
    { value: "1.03", suffix: "×", title: "Ceiling from more nodes", body: "Amdahl's law caps what extra quantum peers can add to one run." },
    { value: "3.2", suffix: "×", title: "Faster at 40 assets", body: "Where QAOA first overtakes the classical baseline." },
    { value: "9.5", suffix: "×", title: "Faster at 60 assets", body: "The gap widens as the problem grows." },
  ],
  footnote: "Simulator benchmarks from the QMesh research draft. QMesh runs on Qiskit statevector simulation, not quantum hardware.",
} as const;

/** A run's receipt, printed line by line on scroll. Every line is a real step in the codebase. */
export const RECEIPT = {
  title: ["Every result leaves", "a receipt."],
  body: "Each run records what was asked, how it was paid, where it ran and how to check it, then pins that record where anyone can fetch it.",
  counterLabel: "Events on one receipt",
  chip: "Pinned by CID",
  head: ["Receipt", "Example job"],
  groups: [
    {
      name: "01 Request",
      tag: "x402",
      lines: [
        ["Submit OpenQASM circuit", "2 qubits"],
        ["402 Payment Required", "x402"],
        ["Pay in USDC", "Algorand TestNet"],
      ],
    },
    {
      name: "02 Plan",
      tag: "Coordinator",
      lines: [
        ["Normalize the circuit", "QASM"],
        ["Build the execution plan", "Fragments"],
        ["Reserve peer capacity", "libp2p"],
      ],
    },
    {
      name: "03 Run",
      tag: "Peers",
      lines: [
        ["Send fragments over streams", "libp2p"],
        ["Statevector simulation", "Qiskit"],
        ["Measure and assemble", "Result"],
      ],
    },
    {
      name: "04 Prove",
      tag: "Provenance",
      lines: [
        ["Hash inputs, plan and results", "Bundle"],
        ["Pin the bundle to IPFS", "CID"],
        ["Fetch by CID, hashes match", "Verified"],
        ["Merkle anchor on Sepolia", "In review"],
      ],
    },
  ],
} as const;

export const DEVELOPERS = {
  title: "Start building today",
  subtitle: "One request, one payment, one receipt",
  checks: [
    { title: "Plain REST", body: "OpenQASM in, a job ID out" },
    { title: "Machine-payable", body: "x402 settles each run in Algorand USDC" },
    { title: "Open source", body: "Coordinator, workers and console under Apache 2.0" },
    { title: "Testnets only", body: "No mainnet, no real money, ever" },
  ],
  primary: "Open the console",
  secondary: "Read the docs",
  request: `curl -X POST "$QMESH/api/x402/quantum/runs" \\
  -H "Content-Type: application/json" \\
  -d '{
    "circuit": "OPENQASM 2.0; include \\"qelib1.inc\\"; qreg q[2]; creg c[2]; h q[0]; cx q[0],q[1]; measure q -> c;"
  }'`,
  challenge: `HTTP/1.1 402 Payment Required
# pay the requirement in Algorand USDC, then retry`,
  response: `HTTP/1.1 201 Created
{
  "job_id": "job_8d0f5af2fd3640be8d62a9f48f8d3d6d",
  "status": "queued"
}`,
  cards: [
    { title: "Repository", body: "Coordinator, workers, console and contracts.", href: REPOSITORY_URL },
    { title: "Research paper", body: "Where quantum wins, and where it does not.", href: RESEARCH_URL },
    { title: "x402 docs", body: "Request flow and TestNet verification.", href: DOCS.X402 },
    { title: "Provenance", body: "Bundles, commitments and what they prove.", href: DOCS.PROVENANCE },
  ],
} as const;

export interface TeamMember {
  name: string;
  role: string;
  /** GitHub login; omitted when it is not known for certain. */
  github?: string;
}

// Seeded from the repository's commit history. Edit roles and add people here.
export const TEAM: { title: string; body: string; members: ReadonlyArray<TeamMember> } = {
  title: "The people building the mesh",
  body: "QMesh is built in the open. Every contributor below has commits in the repository.",
  members: [
    { name: "Soham Bhoir", role: "Maintainer", github: "Winter-Soren" },
    { name: "Harshal Dulera", role: "Contributor", github: "harshaldulera" },
    { name: "Saish Korgaonkar", role: "Contributor", github: "SaishKorgaonkar" },
    { name: "Neha Kumari", role: "Contributor", github: "Nkovaturient" },
    { name: "Ishika Bhoyar", role: "Contributor", github: "ishikabhoyar" },
    { name: "Vinay Sitaram Kanse", role: "Contributor" },
    { name: "K Shan", role: "Contributor" },
    { name: "Manu Sheel Gupta", role: "Contributor" },
  ],
};

export const FAQ = {
  title: "Questions, answered plainly",
  items: [
    {
      question: "Does QMesh run on quantum hardware?",
      answer: "No. Circuits run on Qiskit statevector simulation across worker peers. The network, payments and provenance are real; the qubits are simulated.",
    },
    {
      question: "What is a peer?",
      answer: "A process that advertises quantum services over libp2p. The coordinator discovers peers, reserves capacity on them and sends them circuit fragments.",
    },
    {
      question: "How do I know a result wasn't changed?",
      answer: "Each run produces a provenance bundle that hashes its inputs, plan and results. You can re-check it locally and fetch it from IPFS by CID.",
    },
    {
      question: "Does it touch real money or mainnet?",
      answer: "No. Every chain QMesh writes to is a testnet. Robinhood Chain price feeds are only read, never traded.",
    },
    {
      question: "Is it open source?",
      answer: "Yes. The coordinator, workers, console and contracts are on GitHub under Apache 2.0.",
    },
  ],
} as const;

export const CLOSING = {
  title: "Run your first circuit across the mesh.",
  primary: "Open the console",
} as const;

export const FOOTER = {
  blurb: "Quantum computation as discoverable, payable and verifiable network services.",
  scope: "Open-source research platform. Simulated qubits, real network, testnets only.",
  columns: [
    {
      title: "Product",
      links: [
        { label: "Operator console", href: CONSOLE_HREF },
        { label: "Demo video", href: DEMO_URL },
        { label: "Architecture", href: "#architecture" },
      ],
    },
    {
      title: "Developers",
      links: [
        { label: "Repository", href: REPOSITORY_URL },
        { label: "Backend", href: DOCS.BACKEND },
        { label: "x402", href: DOCS.X402 },
        { label: "Chain registry", href: DOCS.CHAIN_REGISTRY },
      ],
    },
    {
      title: "Research",
      links: [
        { label: "Research paper", href: RESEARCH_URL },
        { label: "Provenance", href: DOCS.PROVENANCE },
        { label: "Overview", href: DOCS.OVERVIEW },
      ],
    },
  ],
  wordmark: "QMesh",
  copy: "©2026 QMesh. Open source under Apache 2.0. Simulated qubits, real network.",
} as const;
