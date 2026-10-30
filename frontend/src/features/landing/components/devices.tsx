import styles from "../landing.module.css";
import { add, Box, iso, Led, plane, pts, type V3 } from "./iso";
import { hash } from "./pixel-canvas";

export type Kind = "laptop" | "phone" | "crt" | "cluster" | "pi" | "mini";

// Isometric device drawings shared by the hero map and the architecture's peer-mesh layer.
// Each draws around its own ground centre; callers translate and scale it.

/** A screen's worth of flickering pixel cells, drawn flat in a w×h box. */
function Activity({ w, h, t, seed, level }: { w: number; h: number; t: number; seed: number; level: number }) {
  const cols = 9;
  const rows = 6;
  const cw = w / cols;
  const ch = h / rows;
  const frame = Math.floor(t * 7);
  const cells = [];
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const v = hash(c + seed * 31, r + frame * 3);
      if (v > 1 - level) {
        cells.push(
          <rect
            key={`${r}-${c}`}
            className={v > 1 - level * 0.25 ? styles.isoCellHot : styles.isoCell}
            x={c * cw + 0.6}
            y={r * ch + 0.6}
            width={cw - 1.2}
            height={ch - 1.2}
          />,
        );
      }
    }
  }
  return <>{cells}</>;
}

// ── Devices ──

export interface DrawProps {
  t: number;
  level: number; // 0 idle … 1 computing
  seed: number;
}

function Laptop({ t, level, seed }: DrawProps) {
  const W = 94;
  const D = 62;
  const H = 4;
  const L = 64;
  const tilt = (14 * Math.PI) / 180;
  const o: V3 = [-W / 2, -D / 2, 0];
  const hinge = add(o, [0, 0, H]);
  const lidTop = add(hinge, [0, -L * Math.sin(tilt), L * Math.cos(tilt)]);
  const down: V3 = [0, L * Math.sin(tilt), -L * Math.cos(tilt)];
  const back: V3 = [0, -2.5 * Math.cos(tilt), -2.5 * Math.sin(tilt)];
  const right: V3 = [W, 0, 0];
  return (
    <>
      <Box o={o} w={W} d={D} h={H} />
      <g transform={plane(add(o, [0, 0, H]), [W, 0, 0], [0, D, 0], W, D)}>
        {Array.from({ length: 3 }, (_, r) =>
          Array.from({ length: 10 }, (_, c) => (
            <rect
              key={`${r}-${c}`}
              className={styles.isoKey}
              x={9 + c * 7.8}
              y={8 + r * 8}
              width={6.2}
              height={6}
              vectorEffect="non-scaling-stroke"
            />
          )),
        )}
        <rect className={styles.isoKey} x={33} y={36} width={28} height={20} vectorEffect="non-scaling-stroke" />
      </g>
      <polygon
        className={styles.isoSide}
        points={pts([add(lidTop, right), add(hinge, right), add(add(hinge, right), back), add(add(lidTop, right), back)])}
      />
      <polygon className={styles.isoLid} points={pts([lidTop, add(lidTop, right), add(hinge, right), hinge])} />
      <g transform={plane(lidTop, right, down, W, L)}>
        <rect className={styles.isoScreen} x={5} y={5} width={W - 10} height={L - 12} vectorEffect="non-scaling-stroke" />
        <g transform="translate(5 5)">
          <Activity w={W - 10} h={L - 12} t={t} seed={seed} level={level} />
        </g>
      </g>
    </>
  );
}

function Phone({ t, level, seed }: DrawProps) {
  const w = 38;
  const d = 74;
  const h = 6;
  const o: V3 = [-w / 2, -d / 2, 0];
  return (
    <>
      <Box o={o} w={w} d={d} h={h} />
      <g transform={plane(add(o, [0, 0, h]), [w, 0, 0], [0, d, 0], w, d)}>
        <rect className={styles.isoScreen} x={3.5} y={9} width={w - 7} height={d - 21} vectorEffect="non-scaling-stroke" />
        <g transform="translate(3.5 9)">
          <Activity w={w - 7} h={d - 21} t={t} seed={seed} level={level} />
        </g>
        {/* It is an old phone: a hairline crack and a home button. */}
        <polyline className={styles.isoCrack} points="6,14 13,22 11,30 19,37" vectorEffect="non-scaling-stroke" />
        <circle className={styles.isoKey} cx={w / 2} cy={d - 6} r={3} vectorEffect="non-scaling-stroke" />
      </g>
    </>
  );
}

function Crt({ t, level, seed }: DrawProps) {
  const screen: V3 = [-31, 18, 70];
  return (
    <>
      <Box o={[-14, -16, 0]} w={28} d={22} h={10} />
      <Box o={[-24, -26, 14]} w={48} d={30} h={46} />
      <Box o={[-31, 4, 10]} w={62} d={14} h={60} />
      <g transform={plane(screen, [62, 0, 0], [0, 0, -60], 62, 60)}>
        <rect className={styles.isoScreen} x={7} y={7} width={48} height={38} rx={5} vectorEffect="non-scaling-stroke" />
        <g transform="translate(9 9)">
          <Activity w={44} h={34} t={t} seed={seed} level={level} />
        </g>
        {Array.from({ length: 9 }, (_, k) => (
          <line
            key={k}
            className={styles.isoScan}
            x1={8}
            x2={54}
            y1={9 + k * 4}
            y2={9 + k * 4}
            vectorEffect="non-scaling-stroke"
          />
        ))}
        <rect className={styles.isoKey} x={44} y={50} width={10} height={4} vectorEffect="non-scaling-stroke" />
      </g>
      <Box o={[-30, 26, 0]} w={60} d={18} h={3} />
    </>
  );
}

function PiBoard({ o, t, seed, ports }: { o: V3; t: number; seed: number; ports: boolean }) {
  const pins = [];
  for (let k = 0; k < 18; k += 1) {
    for (const row of [3, 6]) {
      const [x, y] = iso(add(o, [8 + k * 4, row, 4.5]));
      pins.push(<circle key={`${k}-${row}`} className={styles.isoPin} cx={x} cy={y} r={0.9} />);
    }
  }
  return (
    <>
      <Box o={o} w={88} d={58} h={2.5} topClass={styles.isoPcb} />
      {pins}
      <Box o={add(o, [28, 18, 2.5])} w={16} d={16} h={2.4} />
      <Box o={add(o, [50, 21, 2.5])} w={11} d={9} h={1.6} />
      {ports ? (
        <>
          <Box o={add(o, [70, 5, 2.5])} w={18} d={14} h={13} />
          <Box o={add(o, [70, 22, 2.5])} w={18} d={14} h={13} />
          <Box o={add(o, [68, 40, 2.5])} w={20} d={16} h={11} />
        </>
      ) : null}
      <Led at={add(o, [6, 52, 3])} on={Math.floor(t * 6 + seed) % 3 === 0} />
      <Led at={add(o, [12, 52, 3])} on />
    </>
  );
}

function Pi({ t, seed }: DrawProps) {
  return <PiBoard o={[-44, -29, 0]} t={t} seed={seed} ports />;
}

function Cluster({ t, seed }: DrawProps) {
  const o: V3 = [-44, -29, 0];
  const post = (x: number, y: number) => (
    <polyline key={`${x}-${y}`} className={styles.isoEdge} points={pts([add(o, [x, y, 0]), add(o, [x, y, 46])])} />
  );
  return (
    <>
      {post(3, 3)}
      {post(85, 3)}
      {post(3, 55)}
      <PiBoard o={o} t={t} seed={seed} ports={false} />
      <PiBoard o={add(o, [0, 0, 22])} t={t} seed={seed + 1} ports={false} />
      <PiBoard o={add(o, [0, 0, 44])} t={t} seed={seed + 2} ports={false} />
      {post(85, 55)}
    </>
  );
}

function Mini({ t, seed }: DrawProps) {
  const o: V3 = [-25, -25, 0];
  return (
    <>
      <Box o={o} w={50} d={50} h={13} />
      <g transform={plane(add(o, [0, 0, 13]), [50, 0, 0], [0, 50, 0], 50, 50)}>
        {Array.from({ length: 6 }, (_, k) => (
          <line
            key={k}
            className={styles.isoScan}
            x1={12}
            x2={38}
            y1={14 + k * 4.5}
            y2={14 + k * 4.5}
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </g>
      <Led at={add(o, [8, 50, 7])} on={Math.floor(t * 5 + seed) % 2 === 0} />
    </>
  );
}

export const DRAW: Record<Kind, (props: DrawProps) => React.ReactNode> = {
  laptop: Laptop,
  phone: Phone,
  crt: Crt,
  cluster: Cluster,
  pi: Pi,
  mini: Mini,
};

