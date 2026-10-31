"use client";

import { ArrowUpRight } from "lucide-react";
import { useMotionValueEvent, useScroll } from "motion/react";
import { useEffect, useRef, useState } from "react";

import type { RESULTS } from "../landing-content";
import styles from "../landing.module.css";
import { hash } from "./pixel-canvas";

type Story = (typeof RESULTS)["story"];

// ── Scroll timeline (0…1 across the pinned track) ──
// Split holds, particles burst into a field, line up by peer, then fall onto the chart.
const T = {
  reveal: [0.0, 0.12],
  toField: [0.28, 0.38],
  toRows: [0.48, 0.58],
  toChart: [0.68, 0.78],
  drawCurve: [0.78, 0.94],
} as const;
const PHASE_AT = [0, 0.3, 0.7]; // where each act begins, for the tabs
const N = 520; // particles
const STRANDS = 7; // strands per peer bundle

const clamp = (n: number) => Math.min(1, Math.max(0, n));
const span = ([a, b]: readonly [number, number], f: number) => clamp((f - a) / (b - a));
const ease = (n: number) => (n < 0.5 ? 4 * n * n * n : 1 - Math.pow(-2 * n + 2, 3) / 2);
const mix = (a: number, b: number, k: number) => a + (b - a) * k;

type Pt = [number, number];
const bezier = (p0: Pt, p1: Pt, p2: Pt, p3: Pt, u: number): Pt => {
  const v = 1 - u;
  return [
    v * v * v * p0[0] + 3 * v * v * u * p1[0] + 3 * v * u * u * p2[0] + u * u * u * p3[0],
    v * v * v * p0[1] + 3 * v * v * u * p1[1] + 3 * v * u * u * p2[1] + u * u * u * p3[1],
  ];
};

/** QAOA speedup over classical by portfolio size. Measured at 40 and 60; shape between is illustrative. */
const speedup = (assets: number) => {
  if (assets <= 20) return 0.55 + (assets - 10) * 0.025; // classical faster at 10–20
  if (assets <= 40) return mix(0.8, 3.2, Math.pow((assets - 20) / 20, 1.6));
  return 3.2 * Math.pow(9.5 / 3.2, (assets - 40) / 20);
};

const ACCENTS = ["--accent-1", "--accent-2", "--accent-3", "--accent-4", "--accent-5"] as const;

export function ResultsStory({ story, paperHref }: { story: Story; paperHref: string }) {
  const track = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const progress = useRef(0);
  const [phase, setPhase] = useState(0);
  const { scrollYProgress } = useScroll({ target: track, offset: ["start start", "end end"] });
  useMotionValueEvent(scrollYProgress, "change", (v) => {
    progress.current = v;
    const next = v >= PHASE_AT[2] ? 2 : v >= PHASE_AT[1] ? 1 : 0;
    setPhase((prev) => (prev === next ? prev : next));
  });

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const css = getComputedStyle(el);
    const color = (name: string) => css.getPropertyValue(name).trim();
    const ink = color("--ink");
    const muted = color("--ink-muted");
    const faint = color("--ink-faint");
    const hair = color("--hairline");
    const accents = ACCENTS.map(color);
    const font = color("--font-data") || "monospace";
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const peers = story.peers.length;

    let W = 0;
    let H = 0;
    let ratio = 1;
    const resize = () => {
      ratio = Math.min(window.devicePixelRatio || 1, 2);
      W = el.clientWidth;
      H = el.clientHeight;
      el.width = Math.round(W * ratio);
      el.height = Math.round(H * ratio);
    };

    // Layout, recomputed per frame from the current size.
    const geo = () => {
      const narrow = W < 720;
      // Narrow screens use the city alone, so labels fit beside the strands and rows.
      const name = (g: number) => (narrow ? story.peers[g].split(" · ")[1] : story.peers[g]);
      const origin: Pt = [W * (narrow ? 0.08 : 0.16), H * 0.56];
      const ends: Pt[] = story.peers.map((_, g) => [W * (narrow ? 0.58 : 0.7), H * (0.32 + g * 0.1)]);
      const strand = (g: number, k: number): [Pt, Pt, Pt, Pt] => {
        const dy = (k - (STRANDS - 1) / 2) * 3.2;
        const end: Pt = [ends[g][0], ends[g][1] + dy];
        return [origin, [origin[0] + W * 0.22, origin[1]], [end[0] - W * 0.24, end[1]], end];
      };
      const clusters: Pt[] = [
        [0.26, 0.4],
        [0.56, 0.32],
        [0.8, 0.46],
        [0.38, 0.72],
        [0.68, 0.72],
      ].map(([x, y]) => [x * W, y * H]);
      const rowX0 = W * (narrow ? 0.3 : 0.26);
      const rowX1 = W * 0.88;
      const rowY = (g: number) => H * (0.32 + g * 0.1);
      const chart = { x0: W * 0.12, x1: W * 0.84, base: H * 0.76, top: H * 0.26 };
      return { origin, ends, strand, clusters, rowX0, rowX1, rowY, chart, narrow, name };
    };

    const ax = (c: ReturnType<typeof geo>["chart"], assets: number) => mix(c.x0, c.x1, (assets - 10) / 50);
    const ay = (c: ReturnType<typeof geo>["chart"], v: number) => c.base - ((v - 1) / 9) * (c.base - c.top);

    let raf = 0;
    let visible = true;
    const start = performance.now();
    const observer = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
    });
    observer.observe(el);

    const draw = () => {
      raf = requestAnimationFrame(draw);
      if (!visible) return;
      const f = progress.current;
      const t = reduce ? 0 : (performance.now() - start) / 1000;
      const g0 = geo();
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.font = `${g0.narrow ? 10 : 11}px ${font}`;
      ctx.textBaseline = "middle";

      const reveal = ease(span(T.reveal, f));
      const kField = ease(span(T.toField, f));
      const kRows = ease(span(T.toRows, f));
      const kChart = ease(span(T.toChart, f));
      const kCurve = ease(span(T.drawCurve, f));
      const strandsAlpha = 1 - kField;

      // ── Act 1: strands from the circuit out to each peer ──
      if (strandsAlpha > 0.01) {
        ctx.lineWidth = 1;
        for (let g = 0; g < peers; g += 1) {
          for (let k = 0; k < STRANDS; k += 1) {
            const [p0, p1, p2, p3] = g0.strand(g, k);
            ctx.strokeStyle = ink;
            ctx.globalAlpha = 0.16 * strandsAlpha;
            ctx.beginPath();
            const steps = 48;
            for (let s = 0; s <= steps * reveal; s += 1) {
              const [x, y] = bezier(p0, p1, p2, p3, s / steps);
              if (s === 0) ctx.moveTo(x, y);
              else ctx.lineTo(x, y);
            }
            ctx.stroke();
          }
          // The peer's dotted stack and label, like Giga's sources.
          const [ex, ey] = g0.ends[g];
          ctx.globalAlpha = strandsAlpha * reveal;
          ctx.fillStyle = muted;
          for (let k = 0; k < STRANDS; k += 1) ctx.fillRect(ex + 6, ey + (k - 3) * 3.2 - 0.75, 1.5, 1.5);
          ctx.fillStyle = muted;
          ctx.fillText(g0.name(g), ex + 18, ey);
        }
        ctx.globalAlpha = strandsAlpha;
        ctx.fillStyle = ink;
        ctx.fillRect(g0.origin[0] - 3, g0.origin[1] - 3, 6, 6);
        if (g0.narrow) {
          ctx.fillText(story.origin, g0.origin[0] - 3, g0.origin[1] - 16);
        } else {
          ctx.textAlign = "right";
          ctx.fillText(story.origin, g0.origin[0] - 12, g0.origin[1]);
          ctx.textAlign = "left";
        }
      }

      // ── Act 2 labels: legend while scattered, row labels once lined up ──
      const rowsAlpha = kRows * (1 - kChart);
      if (kField > 0.01 && kChart < 0.99) {
        if (rowsAlpha > 0.01) {
          ctx.globalAlpha = rowsAlpha;
          ctx.fillStyle = muted;
          for (let g = 0; g < peers; g += 1) {
            ctx.textAlign = "right";
            ctx.fillText(g0.name(g), g0.rowX0 - 16, g0.rowY(g));
          }
          ctx.textAlign = "left";
          ctx.fillStyle = faint;
          ctx.fillText(story.runAxis[0].toUpperCase(), g0.rowX0, g0.rowY(0) - 26);
          ctx.textAlign = "right";
          ctx.fillText(story.runAxis[1].toUpperCase(), g0.rowX1, g0.rowY(0) - 26);
          ctx.fillText(story.runNote.toUpperCase(), g0.rowX1, g0.rowY(peers - 1) + 30);
          ctx.textAlign = "left";
        }
        const legendAlpha = kField * (1 - kRows);
        if (legendAlpha > 0.01) {
          ctx.globalAlpha = legendAlpha;
          // Centre the legend on its measured width.
          const widths = story.peers.map((p) => ctx.measureText(p.split(" · ")[1]).width + (g0.narrow ? 22 : 34));
          let lx = Math.max(8, W / 2 - widths.reduce((a, b) => a + b, 0) / 2);
          for (let g = 0; g < peers; g += 1) {
            ctx.fillStyle = accents[g];
            ctx.fillRect(lx, H * 0.29 - 2, 4, 4);
            ctx.fillStyle = muted;
            const name = story.peers[g].split(" · ")[1];
            ctx.fillText(name, lx + 10, H * 0.29);
            lx += widths[g];
          }
        }
      }

      // ── Soft glow behind each peer's cluster while the field is scattered ──
      const nebula = kField * (1 - kRows);
      if (nebula > 0.01) {
        for (let g = 0; g < peers; g += 1) {
          const [gx, gy] = g0.clusters[g];
          const r = W * 0.16;
          const glow = ctx.createRadialGradient(gx, gy, 0, gx, gy, r);
          glow.addColorStop(0, accents[g]);
          glow.addColorStop(1, "transparent");
          ctx.globalAlpha = 0.07 * nebula;
          ctx.fillStyle = glow;
          ctx.fillRect(gx - r, gy - r, r * 2, r * 2);
        }
      }

      // ── Particles: one population morphing through every act ──
      const c = g0.chart;
      for (let i = 0; i < N; i += 1) {
        const g = i % peers;
        const k = Math.floor(i / peers) % STRANDS;
        const h1 = hash(i, 1);
        const h2 = hash(i, 2);
        // A: streaming along the strand.
        const [p0, p1, p2, p3] = g0.strand(g, k);
        const u = (h1 + t * (0.05 + h2 * 0.05)) % 1;
        const a = bezier(p0, p1, p2, p3, Math.min(u, reveal));
        // B: scattered in the peer's cluster, drifting.
        const r = Math.sqrt(h2) * W * 0.13;
        const th = h1 * Math.PI * 2 + t * 0.05;
        const b: Pt = [g0.clusters[g][0] + Math.cos(th) * r, g0.clusters[g][1] + Math.sin(th) * r * 0.7];
        // C: lined up in the peer's row, ordered by time.
        const cx = mix(g0.rowX0, g0.rowX1, Math.pow(h1, 0.8));
        const cy = g0.rowY(g) + (Math.floor(h2 * 3) - 1) * 4;
        // D: resting on the curve.
        const assets = 10 + (i / N) * 50;
        const onCurve = assets <= 10 + 50 * kCurve;
        const d: Pt = [ax(c, assets), onCurve ? ay(c, speedup(assets)) : c.base];

        let x = mix(a[0], b[0], kField);
        let y = mix(a[1], b[1], kField);
        x = mix(x, cx, kRows);
        y = mix(y, cy, kRows);
        x = mix(x, d[0], kChart);
        y = mix(y, d[1], kChart);

        const field = kField * (1 - kChart);
        const twinkle = 0.55 + 0.45 * Math.sin(t * 2 + i);
        const rows = kRows * (1 - kChart);
        ctx.globalAlpha = Math.min(
          1,
          strandsAlpha * (reveal > u ? 0.9 : 0) +
            field * (0.45 + 0.55 * twinkle) +
            rows * 0.35 +
            kChart * (onCurve ? 0.5 : 0.18),
        );
        ctx.fillStyle = field > 0.2 ? accents[g] : ink;
        const size = kChart > 0.5 ? 1.4 : rows > 0.5 ? 2.2 : 1.9;
        ctx.fillRect(x - size / 2, y - size / 2, size, size);
      }

      // ── Act 3: the chart ──
      if (kChart > 0.01) {
        ctx.globalAlpha = kChart;
        // Classical baseline (1×).
        ctx.strokeStyle = hair;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(c.x0, c.base);
        ctx.lineTo(c.x1, c.base);
        ctx.stroke();
        ctx.fillStyle = muted;
        ctx.fillText(story.chart.baseline, c.x0, c.base - 14);
        ctx.fillStyle = faint;
        for (const a of [10, 20, 40, 60]) {
          ctx.textAlign = "center";
          ctx.fillText(String(a), ax(c, a), c.base + 18);
        }
        ctx.fillText(story.chart.axis.toUpperCase(), (c.x0 + c.x1) / 2, c.base + 40);
        ctx.textAlign = "left";
        ctx.fillText(story.chart.left, ax(c, 10), c.base + 62);
        const noteY = g0.narrow ? c.base + 80 : c.base + 62;

        // QAOA curve, drawn left to right with a soft glow.
        if (kCurve > 0) {
          const end = 10 + 50 * kCurve;
          const grad = ctx.createLinearGradient(c.x0, 0, c.x1, 0);
          grad.addColorStop(0, faint);
          grad.addColorStop(0.5, accents[1]);
          grad.addColorStop(1, ink);
          ctx.strokeStyle = grad;
          ctx.lineWidth = 1.6;
          ctx.shadowColor = ink;
          ctx.shadowBlur = 10;
          ctx.beginPath();
          for (let a = 10; a <= end; a += 0.5) {
            const x = ax(c, a);
            const y = ay(c, speedup(a));
            if (a === 10) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.stroke();
          ctx.shadowBlur = 0;
          // Head of the line.
          ctx.fillStyle = ink;
          ctx.fillRect(ax(c, end) - 2.5, ay(c, speedup(end)) - 2.5, 5, 5);
          // Measured points, with a gain bracket for the last.
          for (const pt of story.chart.points) {
            if (end < pt.assets) continue;
            const px = ax(c, pt.assets);
            const py = ay(c, pt.speedup);
            ctx.fillStyle = accents[0];
            ctx.beginPath();
            ctx.arc(px, py, 3.5, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = ink;
            ctx.textAlign = "right";
            ctx.fillText(pt.label, px - 10, py - 12);
            ctx.textAlign = "left";
          }
          if (end >= 60 && !g0.narrow) {
            const px = ax(c, 60) + 22;
            ctx.strokeStyle = hair;
            ctx.beginPath();
            ctx.moveTo(px, ay(c, 9.5));
            ctx.lineTo(px, c.base);
            ctx.stroke();
            ctx.fillStyle = muted;
            ctx.fillText(story.chart.series, px + 8, ay(c, 9.5));
          }
          ctx.fillStyle = faint;
          if (g0.narrow) {
            ctx.fillText(story.chart.note.split(";")[0] + ".", ax(c, 10), noteY);
          } else {
            ctx.textAlign = "right";
            ctx.fillText(story.chart.note, c.x1, noteY);
            ctx.textAlign = "left";
          }
        }
      }
      ctx.globalAlpha = 1;
    };

    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      observer.disconnect();
    };
  }, [story]);

  const jump = (k: number) => {
    const el = track.current;
    if (!el) return;
    const top = el.getBoundingClientRect().top + window.scrollY;
    const range = el.offsetHeight - window.innerHeight;
    window.scrollTo({ top: top + range * (PHASE_AT[k] + 0.12), behavior: "smooth" });
  };

  const act = story.phases[phase];
  return (
    <div ref={track} className={styles.storyTrack}>
      <div className={styles.storyStage}>
        <canvas ref={canvas} className={styles.storyCanvas} role="img" aria-label={story.label} />
        <div key={act.key} className={styles.storyTitle}>
          <h3>{act.title}</h3>
          <p>{act.body}</p>
        </div>
        <div className={styles.storyTabs} role="group" aria-label="Story acts">
          {story.phases.map((p, k) => (
            <button key={p.key} type="button" aria-pressed={k === phase} onClick={() => jump(k)}>
              {p.title.replace(".", "").toUpperCase()}
            </button>
          ))}
          <a href={paperHref} target="_blank" rel="noreferrer" className={styles.storyTabLink}>
            {story.action.toUpperCase()} <ArrowUpRight aria-hidden="true" />
          </a>
        </div>
      </div>
    </div>
  );
}
