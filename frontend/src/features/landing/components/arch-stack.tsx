"use client";

import { AnimatePresence, motion, useMotionValueEvent, useScroll } from "motion/react";
import { useRef, useState } from "react";

import type { Layer } from "../landing-content";
import styles from "../landing.module.css";
import { DRAW, type Kind } from "./devices";
import { add, clamp, COS, iso, plane, pts, SIN, type V3 } from "./iso";

// ── Choreography, measured from griffin.com's "built to evolve" section ──
// The intro holds the heading with the plates evenly spread; then each layer
// takes the centre while passed plates stack tightly above and upcoming ones
// compress below.
// Griffin's offsets, opened up so the raised objects on each plate have room.
const INTRO_GAP = 118; // px between plates while the intro heading shows
const SLOTS: ReadonlyArray<[number, number]> = [
  [-4, -560],
  [-3, -490],
  [-2, -415],
  [-1, -330],
  [0, 0],
  [1, 350],
  [2, 505],
  [3, 545],
  [4, 570],
];
const CENTER_Y = 420; // active step and plate centre in the 900-tall stage
const STEP_PITCH = 30; // px between collapsed step labels
const EASE = [0.16, 1, 0.3, 1] as const;
const STAGE = 900; // Griffin's stage height; positions scale with the real viewport
const at = (px: number) => `calc(${(px / STAGE).toFixed(4)} * var(--stage))`;

const slotY = (s: number) => {
  if (s <= SLOTS[0][0]) return SLOTS[0][1];
  for (let k = 1; k < SLOTS.length; k += 1) {
    const [s1, y1] = SLOTS[k];
    const [s0, y0] = SLOTS[k - 1];
    if (s <= s1) return y0 + ((y1 - y0) * (s - s0)) / (s1 - s0);
  }
  return SLOTS[SLOTS.length - 1][1];
};
const smooth = (n: number) => {
  const c = clamp(n);
  return c * c * (3 - 2 * c);
};

// Plate geometry (world units → about 470px wide on screen).
const S = 270;
const T = 10;
const ORIGIN: V3 = [-S / 2, -S / 2, 0];

const ACCENTS = ["var(--accent-1)", "var(--accent-2)", "var(--accent-3)", "var(--accent-4)", "var(--accent-5)"];

export function ArchStack({
  title,
  body,
  layers,
}: {
  title: readonly [string, string];
  body: string;
  layers: ReadonlyArray<Layer>;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [f, setF] = useState(0);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  useMotionValueEvent(scrollYProgress, "change", (value) => setF(Math.round(value * 1000) / 1000));

  const n = layers.length;
  // Intro until 12%, then each layer gets an equal share of the scroll.
  const p = clamp((f - 0.2) / 0.72) * (n - 1);
  const blend = smooth((f - 0.04) / 0.16);
  const intro = f < 0.12;
  const active = intro ? -1 : Math.round(p);
  const settled = !intro && Math.abs(p - active) < 0.22 && blend > 0.98;
  const passedTop = active > 0 ? 80 + (active - 1) * STEP_PITCH + 7 : 0;

  const plateY = (i: number) => {
    const spread = (i - (n - 1) / 2) * INTRO_GAP;
    return spread + (slotY(i - p) - spread) * blend;
  };

  return (
    <div ref={ref} className={styles.archTrack} style={{ height: `${n * 150 + 60}vh` }}>
      <div className={styles.archPin}>
        <div className={styles.archLeft}>
          <span className={styles.archRail} aria-hidden="true" />
          {active >= 0 ? (
            <span
              className={styles.archRailLit}
              aria-hidden="true"
              style={{
                top: at(passedTop),
                height: at(CENTER_Y + 7 - passedTop),
                ["--step-accent" as string]: ACCENTS[active],
              }}
            />
          ) : null}

          <ol className={styles.archSteps} aria-label="Layers">
            {layers.map((layer, i) => {
              const state = i === active ? "active" : i < active ? "passed" : "next";
              const y =
                state === "active"
                  ? CENTER_Y
                  : state === "passed"
                    ? 80 + i * STEP_PITCH
                    : 846 - (n - 1 - i) * STEP_PITCH;
              return (
                <li
                  key={layer.key}
                  className={styles.archStep}
                  data-state={state}
                  style={{ transform: `translateY(${at(y)})`, ["--step-accent" as string]: ACCENTS[i] }}
                  aria-current={state === "active" ? "step" : undefined}
                >
                  <span className={styles.archMarker} aria-hidden="true" />
                  <span className={styles.archStepLabel}>
                    <span>{String(i + 1).padStart(2, "0")}</span>
                    {layer.name.toUpperCase()}
                  </span>
                </li>
              );
            })}
          </ol>

          <AnimatePresence initial={false}>
            {intro ? (
              <motion.div
                key="intro"
                className={styles.archIntro}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0, transition: { duration: 0.5, delay: 0.42, ease: EASE } }}
                exit={{ opacity: 0, y: -10, transition: { duration: 0.18 } }}
              >
                <h2 id="architecture-title" className={styles.h2}>
                  {title[0]} <em>{title[1]}</em>
                </h2>
                <p>{body}</p>
              </motion.div>
            ) : (
              <motion.div
                key={layers[active].key}
                className={styles.archPanel}
                style={{ ["--panel-top" as string]: at(CENTER_Y + 30) }}
                initial={{ opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0, transition: { duration: 0.5, delay: 0.42, ease: EASE } }}
                exit={{ opacity: 0, y: -10, transition: { duration: 0.18 } }}
              >
                <h3 className={styles.archTitle}>{layers[active].title}</h3>
                <p>{layers[active].body}</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className={styles.archVisual}>
          <svg
            className={styles.archSvg}
            viewBox="-350 -440 700 900"
            preserveAspectRatio="xMidYMin meet"
            role="img"
            aria-label={
              active >= 0
                ? `Architecture stack, ${n} layers. ${layers[active].name}: ${layers[active].body}`
                : `Architecture stack, ${n} layers.`
            }
          >
            {/* Bottom layer first so the upper plates paint over it. */}
            {layers
              .map((layer, i) => ({ layer, i }))
              .reverse()
              .map(({ layer, i }) => (
                <g key={layer.key} transform={`translate(0 ${plateY(i)})`}>
                  <Plate kind={layer.key} lit={i === active} />
                </g>
              ))}
            {settled ? (
              <g transform={`translate(0 ${plateY(active)})`}>
                <Callouts key={layers[active].key} labels={layers[active].callouts} accent={ACCENTS[active]} />
              </g>
            ) : null}
          </svg>
        </div>
      </div>
    </div>
  );
}

const top = (x: number, y: number): V3 => add(ORIGIN, [x, y, T]);
/** A point standing z above the plate surface. */
const raised = (x: number, y: number, z: number): V3 => add(top(x, y), [0, 0, z]);

function Plate({ kind, lit }: { kind: Layer["key"]; lit: boolean }) {
  const c = (x: number, y: number, z: number): V3 => add(ORIGIN, [x, y, z]);
  return (
    <g className={styles.plate} data-lit={lit}>
      <polygon className={styles.plateSide} points={pts([c(S, 0, 0), c(S, S, 0), c(S, S, T), c(S, 0, T)])} />
      <polygon className={styles.plateSide} points={pts([c(0, S, 0), c(S, S, 0), c(S, S, T), c(0, S, T)])} />
      <polygon className={styles.plateTop} points={pts([c(0, 0, T), c(S, 0, T), c(S, S, T), c(0, S, T)])} />
      <g transform={plane(top(0, 0), [S, 0, 0], [0, S, 0], 100, 100)}>
        <Drawing kind={kind} />
      </g>
      <Objects kind={kind} />
    </g>
  );
}

// ── Raised objects on each plate (plate-local world units, origin at the plate's top corner) ──

/** An extruded block standing on the plate. */
function Block({ x, y, w, d, h, z = 0, tone = "dark" }: { x: number; y: number; w: number; d: number; h: number; z?: number; tone?: "dark" | "light" }) {
  const c = (dx: number, dy: number, dz: number) => raised(x + dx, y + dy, z + dz);
  return (
    <g className={styles.block} data-tone={tone}>
      <polygon className={styles.blockSide} points={pts([c(w, 0, 0), c(w, d, 0), c(w, d, h), c(w, 0, h)])} />
      <polygon className={styles.blockFront} points={pts([c(0, d, 0), c(w, d, 0), c(w, d, h), c(0, d, h)])} />
      <polygon className={styles.blockTop} points={pts([c(0, 0, h), c(w, 0, h), c(w, d, h), c(0, d, h)])} />
    </g>
  );
}

/** A stack of coins: each one a short cylinder seen isometrically. */
function Coins({ x, y, count, r = 16 }: { x: number; y: number; count: number; r?: number }) {
  const rx = r * Math.SQRT2 * COS;
  const ry = r * Math.SQRT2 * SIN;
  const thick = 4;
  return (
    <g className={styles.coins}>
      {Array.from({ length: count }, (_, k) => {
        const [cx, cy] = iso(raised(x, y, k * thick));
        return (
          <g key={k}>
            <ellipse className={styles.coinSide} cx={cx} cy={cy} rx={rx} ry={ry} />
            <rect className={styles.coinBand} x={cx - rx} y={cy - thick} width={rx * 2} height={thick} />
            <ellipse className={styles.coinTop} cx={cx} cy={cy - thick} rx={rx} ry={ry} />
          </g>
        );
      })}
    </g>
  );
}

/** A line between two raised points on the plate. */
function Wire({ a, b, live }: { a: V3; b: V3; live?: boolean }) {
  return <polyline className={live ? styles.wireLive : styles.wire} points={pts([raised(...a), raised(...b)])} />;
}

/** A device from the hero, standing on a node box. */
function DeviceOn({ kind, x, y, scale = 0.72 }: { kind: Kind; x: number; y: number; scale?: number }) {
  const Draw = DRAW[kind];
  const [px, py] = iso(raised(x, y, 12));
  return (
    <g transform={`translate(${px} ${py}) scale(${scale})`}>
      <Draw t={0} level={0.35} seed={x} />
    </g>
  );
}

function Objects({ kind }: { kind: Layer["key"] }) {
  switch (kind) {
    case "app":
      // A raised console window with panels at different heights, and an API terminal.
      return (
        <>
          <Block x={70} y={22} w={185} d={150} h={6} />
          <Block x={80} y={32} w={78} d={52} h={18} tone="light" />
          <Block x={168} y={32} w={78} d={22} h={10} />
          <Block x={168} y={62} w={34} d={22} h={14} />
          <Block x={80} y={94} w={166} d={68} h={10} />
          <Block x={70} y={190} w={110} d={62} h={22} />
        </>
      );
    case "coordinator":
      // A coordinator server feeding three circuit fragments of different sizes.
      return (
        <>
          <Block x={24} y={32} w={70} d={56} h={64} />
          <Wire a={[94, 60, 40]} b={[140, 150, 30]} live />
          <Wire a={[94, 60, 40]} b={[200, 150, 24]} live />
          <Wire a={[94, 60, 40]} b={[160, 220, 34]} live />
          <Block x={120} y={130} w={40} d={40} h={30} tone="light" />
          <Block x={180} y={130} w={40} d={40} h={24} tone="light" />
          <Block x={140} y={200} w={40} d={40} h={34} tone="light" />
        </>
      );
    case "payments":
      // Coin stacks beside a raised receipt.
      return (
        <>
          <Coins x={60} y={70} count={7} />
          <Block x={150} y={40} w={92} d={130} h={8} />
          <Block x={162} y={52} w={68} d={20} h={4} tone="light" />
          <Coins x={100} y={110} count={10} />
          <Coins x={60} y={150} count={4} />
          <Coins x={110} y={195} count={6} />
        </>
      );
    case "mesh": {
      // Node boxes with the hero's devices on them, wired to each other.
      const nodes: [Kind, number, number][] = [
        ["laptop", 58, 58],
        ["pi", 208, 52],
        ["crt", 134, 136],
        ["phone", 58, 214],
        ["mini", 212, 210],
      ];
      return (
        <>
          {nodes.map(([, x, y], i) =>
            nodes.slice(i + 1).map(([, x2, y2], j) => <Wire key={`${i}-${j}`} a={[x, y, 12]} b={[x2, y2, 12]} live />),
          )}
          {nodes.map(([k, x, y]) => (
            <g key={k}>
              <Block x={x - 32} y={y - 32} w={64} d={64} h={12} />
              <DeviceOn kind={k} x={x} y={y} />
            </g>
          ))}
        </>
      );
    }
    case "provenance": {
      // A Merkle tree in cubes: leaves low, branches higher, the root on top; then the anchor chain.
      const leaf = 12;
      const mid = 30;
      const root = 52;
      return (
        <>
          <Block x={118} y={22} w={34} d={34} h={root} tone="light" />
          <Wire a={[135, 40, root]} b={[85, 110, mid]} />
          <Wire a={[135, 40, root]} b={[185, 110, mid]} />
          <Block x={70} y={95} w={30} d={30} h={mid} />
          <Block x={170} y={95} w={30} d={30} h={mid} />
          {[50, 120].map((x) => (
            <Wire key={x} a={[85, 110, mid]} b={[x, 190, leaf]} />
          ))}
          {[150, 220].map((x) => (
            <Wire key={x} a={[185, 110, mid]} b={[x, 190, leaf]} />
          ))}
          {[50, 120, 150, 220].map((x) => (
            <Block key={x} x={x - 14} y={176} w={28} d={28} h={leaf} />
          ))}
        </>
      );
    }
  }
}

/** Griffin-style plate art, drawn flat on 100×100 and mapped onto the plate: black panels, hairlines, bars. */
function Drawing({ kind }: { kind: Layer["key"] }) {
  const ink = { className: styles.plateInk, vectorEffect: "non-scaling-stroke" as const };
  const bar = { className: styles.plateBar };
  const hatch = (x: number, y: number, w: number, h: number, step = 2.2) =>
    Array.from({ length: Math.floor(w / step) }, (_, k) => (
      <line key={`h${x}-${k}`} {...ink} x1={x + k * step} y1={y} x2={x + k * step} y2={y + h} />
    ));
  const label = (text: string, x: number, y: number) => (
    <text className={styles.plateText} x={x} y={y}>
      {text}
    </text>
  );
  switch (kind) {
    case "app":
      return (
        <>
          <rect {...ink} x={4} y={4} width={92} height={92} />
          {hatch(8, 8, 14, 84)}
          {label("QMESH:CONSOLE", 60, 94)}
        </>
      );
    case "coordinator":
      return (
        <>
          {label("PLAN:QASM", 8, 12)}
          {[60, 68, 82, 90].map((y, k) => (
            <rect key={y} {...bar} x={6 + k * 3} y={y} width={[34, 40, 22, 30][k]} height={3.2} rx={1.6} />
          ))}
          {[44, 66].map((x) => (
            <line key={x} {...ink} className={styles.plateCut} x1={x} y1={44} x2={x} y2={96} />
          ))}
        </>
      );
    case "payments":
      return (
        <>
          <rect {...ink} x={4} y={4} width={92} height={92} />
          {Array.from({ length: 34 }, (_, k) => (
            <rect
              key={k}
              {...bar}
              x={52 + k * 1.2}
              y={k % 3 === 0 ? 78 : 81}
              width={k % 4 === 0 ? 0.9 : 0.5}
              height={k % 3 === 0 ? 12 : 9}
            />
          ))}
          {label("X402:USDC", 8, 94)}
        </>
      );
    case "mesh":
      return (
        <>
          {Array.from({ length: 5 }, (_, r) =>
            Array.from({ length: 5 }, (_, k) => (
              <text key={`${r}-${k}`} className={styles.plateCross} x={8 + k * 21} y={10 + r * 21}>
                +
              </text>
            )),
          )}
          {label("PEER:MESH", 8, 97)}
        </>
      );
    case "provenance":
      return (
        <>
          {Array.from({ length: 40 }, (_, k) => (
            <rect
              key={k}
              {...bar}
              x={8 + k * 2}
              y={k % 5 === 0 ? 84 : 86}
              width={k % 3 === 0 ? 1.4 : 0.7}
              height={k % 5 === 0 ? 10 : 8}
            />
          ))}
          {label("IPFS:CID", 8, 80)}
        </>
      );
  }
}

/** Two-line mono labels on angled leaders, like Griffin's: dot, label, a diagonal, then straight down to the plate. */
function Callouts({ labels, accent }: { labels: readonly [string, string]; accent: string }) {
  const specs: { anchor: V3; label: [number, number]; side: "left" | "right" }[] = [
    { anchor: top(S * 0.2, S * 0.62), label: [-235, -215], side: "left" },
    { anchor: top(S * 0.72, S * 0.12), label: [150, -165], side: "right" },
  ];
  return (
    <motion.g
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4, ease: EASE }}
      style={{ ["--step-accent" as string]: accent }}
    >
      {specs.map(({ anchor, label: [lx, ly], side }, k) => {
        const [ax, ay] = iso(anchor);
        const words = labels[k].toUpperCase().split(" ");
        const cut = Math.ceil(words.length / 2);
        const lines = words.length > 1 ? [words.slice(0, cut).join(" "), words.slice(cut).join(" ")] : words;
        const textW = Math.max(...lines.map((l) => l.length)) * 8.4;
        // The leader leaves the label, runs diagonally to a knee, then drops to the anchor.
        const startX = side === "left" ? lx + 18 + textW + 8 : lx - 8;
        const kneeY = ly + 34;
        return (
          <g key={labels[k]}>
            <polyline className={styles.calloutLine} points={`${startX},${ly - 4} ${ax},${kneeY} ${ax},${ay}`} />
            <circle className={styles.calloutDot} cx={lx + 4} cy={ly - 5} r={3.5} />
            <text className={styles.calloutText} x={lx + 18} y={ly}>
              {lines.map((line, j) => (
                <tspan key={line} x={lx + 18} dy={j === 0 ? 0 : 18}>
                  {line}
                </tspan>
              ))}
            </text>
          </g>
        );
      })}
    </motion.g>
  );
}
