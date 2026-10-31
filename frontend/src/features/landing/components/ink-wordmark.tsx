"use client";

import { useEffect, useRef } from "react";

import styles from "../landing.module.css";
import { hash } from "./pixel-canvas";

type Blot = { x: number; y: number; r: number; max: number; born: number; seed: number };

/**
 * The footer wordmark as blueprint line art: hairline letter outlines with
 * construction ticks and a crosshair in each letter. Moving over it floods the
 * letters with ink that spreads in organic blots, then slowly recedes.
 */
export function InkWordmark({ word }: { word: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const el = ref.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    const css = getComputedStyle(el);
    const ink = css.getPropertyValue("--ink").trim();
    const line = css.getPropertyValue("--ink-muted").trim();
    const faint = css.getPropertyValue("--ink-faint").trim();
    const mark = css.getPropertyValue("--accent-4").trim();
    const family = css.getPropertyValue("--font-text").trim() || "sans-serif";
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // Offscreen layers: the ink mask, and the solid letters it reveals.
    const mask = document.createElement("canvas");
    const mctx = mask.getContext("2d");
    const solid = document.createElement("canvas");
    const sctx = solid.getContext("2d");
    if (!mctx || !sctx) return;

    let W = 0;
    let H = 0;
    let ratio = 1;
    let size = 0;
    let glyphs: { x: number; w: number; ch: string }[] = [];
    let baseline = 0;
    let capTop = 0;

    const layout = () => {
      ratio = Math.min(window.devicePixelRatio || 1, 2);
      W = el.clientWidth;
      H = el.clientHeight;
      for (const c of [el, mask, solid]) {
        c.width = Math.round(W * ratio);
        c.height = Math.round(H * ratio);
      }
      // Fit the word to the width, with letter spacing like the reference.
      size = H * 1.08;
      ctx.font = `500 ${size}px ${family}`;
      const gap = size * 0.07;
      let total = [...word].reduce((s, ch) => s + ctx.measureText(ch).width, 0) + gap * (word.length - 1);
      const fit = (W * 0.95) / total;
      size *= Math.min(1, fit);
      ctx.font = `500 ${size}px ${family}`;
      const g2 = size * 0.07;
      total = [...word].reduce((s, ch) => s + ctx.measureText(ch).width, 0) + g2 * (word.length - 1);
      let x = (W - total) / 2;
      glyphs = [...word].map((ch) => {
        const w = ctx.measureText(ch).width;
        const g = { x, w, ch };
        x += w + g2;
        return g;
      });
      const m = ctx.measureText("H");
      const cap = m.actualBoundingBoxAscent;
      baseline = H / 2 + cap / 2;
      capTop = baseline - cap;
    };

    let blots: Blot[] = [];
    let pointer: { x: number; y: number; t: number } | null = null;
    let last = 0;
    const start = performance.now();

    const blotPath = (c: CanvasRenderingContext2D, b: Blot, t: number) => {
      // An organic edge: radius wobbles with low-frequency noise around the circle.
      const steps = 36;
      c.beginPath();
      for (let k = 0; k <= steps; k += 1) {
        const a = (k / steps) * Math.PI * 2;
        const wob =
          0.78 +
          0.22 * Math.sin(a * 3 + b.seed * 9 + t * 0.4) +
          0.12 * Math.sin(a * 7 + b.seed * 21) +
          0.08 * Math.sin(a * 13 + b.seed * 5);
        const r = b.r * wob;
        const px = b.x + Math.cos(a) * r;
        const py = b.y + Math.sin(a) * r;
        if (k === 0) c.moveTo(px, py);
        else c.lineTo(px, py);
      }
      c.closePath();
    };

    const draw = (now: number) => {
      const t = (now - start) / 1000;
      const dt = last ? Math.min(0.05, t - last) : 0;
      last = t;

      // Grow while the pointer is near, recede once it has gone.
      const active = pointer && t - pointer.t < 0.15;
      blots.forEach((b) => {
        const age = t - b.born;
        if (age < 1.2) b.r += (b.max - b.r) * Math.min(1, dt * 4);
        else if (!active || age > 2.5) b.r -= dt * b.max * 0.35;
      });
      blots = blots.filter((b) => b.r > 1);

      // Ink mask.
      mctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      mctx.clearRect(0, 0, W, H);
      mctx.fillStyle = "#000";
      for (const b of blots) {
        blotPath(mctx, b, t);
        mctx.fill();
        // Splash droplets around the rim.
        for (let k = 0; k < 4; k += 1) {
          const a = hash(b.seed * 13, k) * Math.PI * 2;
          const d = b.r * (1.05 + hash(k, b.seed * 7) * 0.35);
          const rr = b.r * (0.06 + hash(b.seed, k * 3) * 0.08);
          mctx.beginPath();
          mctx.arc(b.x + Math.cos(a) * d, b.y + Math.sin(a) * d, rr, 0, Math.PI * 2);
          mctx.fill();
        }
      }

      // Solid letters, kept only where the ink mask has paint.
      sctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      sctx.globalCompositeOperation = "source-over";
      sctx.clearRect(0, 0, W, H);
      sctx.font = `500 ${size}px ${family}`;
      sctx.textBaseline = "alphabetic";
      sctx.fillStyle = ink;
      for (const g of glyphs) sctx.fillText(g.ch, g.x, baseline);
      sctx.globalCompositeOperation = "destination-in";
      sctx.setTransform(1, 0, 0, 1, 0, 0);
      sctx.drawImage(mask, 0, 0);

      // Compose: blueprint outlines, construction marks, then the ink.
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.font = `500 ${size}px ${family}`;
      ctx.textBaseline = "alphabetic";
      ctx.lineWidth = 1;
      ctx.strokeStyle = line;
      for (const g of glyphs) ctx.strokeText(g.ch, g.x, baseline);

      // Construction ticks at each glyph's box corners and mid-height, and a centre crosshair.
      ctx.strokeStyle = faint;
      const narrow = W < 640;
      const tick = narrow ? 3 : Math.max(6, size * 0.035);
      const mid = (capTop + baseline) / 2;
      for (const g of glyphs) {
        const xs = [g.x + size * 0.02, g.x + g.w - size * 0.02];
        for (const x of xs) {
          for (const y of narrow ? [capTop, baseline] : [capTop, mid, baseline]) {
            ctx.beginPath();
            ctx.moveTo(x - tick, y);
            ctx.lineTo(x + tick, y);
            ctx.moveTo(x, y - tick * 0.6);
            ctx.lineTo(x, y + tick * 0.6);
            ctx.stroke();
          }
        }
        const cx = g.x + g.w / 2;
        ctx.beginPath();
        ctx.moveTo(cx - tick * 0.6, mid);
        ctx.lineTo(cx + tick * 0.6, mid);
        ctx.moveTo(cx, mid - tick * 0.6);
        ctx.lineTo(cx, mid + tick * 0.6);
        ctx.stroke();
      }

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(solid, 0, 0);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

      // The small marker square at the pointer, as in the reference.
      if (pointer && t - pointer.t < 1.2) {
        ctx.globalAlpha = 1 - Math.max(0, t - pointer.t - 0.6) / 0.6;
        ctx.fillStyle = mark;
        ctx.fillRect(pointer.x - 5, pointer.y - 5, 10, 10);
        ctx.strokeStyle = mark;
        ctx.strokeRect(pointer.x - 9, pointer.y - 9, 18, 18);
        ctx.globalAlpha = 1;
      }
    };

    let raf = 0;
    let visible = true;
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      if (!visible) return;
      draw(now);
    };

    const onMove = (e: PointerEvent) => {
      const box = el.getBoundingClientRect();
      const x = e.clientX - box.left;
      const y = e.clientY - box.top;
      const t = (performance.now() - start) / 1000;
      const prev = blots[blots.length - 1];
      // Lay a new blot every few pixels of travel; each grows into its neighbours.
      if (!prev || Math.hypot(prev.x - x, prev.y - y) > size * 0.08 || t - prev.born > 0.35) {
        blots.push({ x, y, r: 2, max: size * (0.16 + Math.random() * 0.12), born: t, seed: Math.random() * 100 });
        if (blots.length > 60) blots.shift();
      }
      pointer = { x, y, t };
    };

    layout();
    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
    });
    io.observe(el);
    const ro = new ResizeObserver(() => {
      layout();
      draw(performance.now());
    });
    ro.observe(el);
    // Fonts load late; re-measure once they are ready.
    void document.fonts.ready.then(() => {
      layout();
      draw(performance.now());
    });
    if (reduce) {
      draw(performance.now());
    } else {
      el.addEventListener("pointermove", onMove);
      raf = requestAnimationFrame(loop);
    }
    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      ro.disconnect();
      el.removeEventListener("pointermove", onMove);
    };
  }, [word]);

  return <canvas ref={ref} className={styles.inkCanvas} role="img" aria-label={word} />;
}
