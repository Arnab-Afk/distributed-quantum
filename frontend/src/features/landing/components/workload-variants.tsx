"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { Check } from "lucide-react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import type { Workload } from "../landing-content";
import styles from "../landing.module.css";
import { WorkloadVisual } from "./workload-visuals";

const ADVANCE_MS = 7000;

// ── A · Mesh console (griffin.com "Designed to help you build") ──
// Accordion that auto-advances with a progress line; the panel wipes between a live
// diagram and the CLI for the open workload.
export function MeshConsole({ items }: { items: ReadonlyArray<Workload> }) {
  const [active, setActive] = useState(0);
  const [view, setView] = useState<"mesh" | "cli">("mesh");
  const [paused, setPaused] = useState(false);
  const [tick, setTick] = useState(0);
  const item = items[active];

  useEffect(() => {
    if (paused || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setTimeout(() => setActive((a) => (a + 1) % items.length), ADVANCE_MS);
    return () => window.clearTimeout(id);
  }, [active, paused, items.length, tick]);

  return (
    <div className={styles.wlConsole} onPointerEnter={() => setPaused(true)} onPointerLeave={() => setPaused(false)}>
      <ul className={styles.wlAccordion}>
        {items.map((w, i) => {
          const open = i === active;
          return (
            <li key={w.title} data-open={open}>
              <button
                type="button"
                aria-expanded={open}
                onClick={() => {
                  setActive(i);
                  setTick((t) => t + 1);
                }}
              >
                {w.title}
              </button>
              <div className={styles.wlAccBody} data-open={open}>
                <div>
                  <p>{w.body}</p>
                  <span className={styles.wlFact}>{w.fact}</span>
                </div>
              </div>
              <span
                className={styles.wlProgress}
                data-run={open && !paused}
                key={`${active}-${tick}`}
                style={{ animationDuration: `${ADVANCE_MS}ms` }}
                aria-hidden="true"
              />
            </li>
          );
        })}
      </ul>
      <div className={styles.wlPanel}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={`${item.title}-${view}`}
            className={styles.wlPanelInner}
            initial={{ clipPath: "inset(0 0 0 100%)" }}
            animate={{ clipPath: "inset(0 0 0 0%)" }}
            exit={{ clipPath: "inset(0 100% 0 0)" }}
            transition={{ duration: 0.6, ease: [0.65, 0, 0.35, 1] }}
          >
            {view === "mesh" ? (
              <WorkloadVisual kind={item.visual} />
            ) : (
              <pre className={styles.wlCode}>
                <code>{`$ ${item.file}\n\n${item.code}\n\n${item.output}`}</code>
              </pre>
            )}
          </motion.div>
        </AnimatePresence>
        <div className={styles.wlToggle} role="group" aria-label="Diagram or command line">
          {(["mesh", "cli"] as const).map((v) => (
            <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}>
              {v.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── B · Scroll index (modal.com "Container infrastructure that won't box you in") ──
// A sticky index beside stacked workload panels; the index follows the scroll.
export function ScrollIndex({ items }: { items: ReadonlyArray<Workload> }) {
  const [active, setActive] = useState(0);
  const refs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.index));
        }
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    refs.current.forEach((el) => el && io.observe(el));
    return () => io.disconnect();
  }, []);

  return (
    <div className={styles.wlScroll}>
      <ol className={styles.wlIndex}>
        {items.map((w, i) => (
          <li key={w.title} data-active={i === active}>
            <a
              href={`#wl-${i}`}
              onClick={(e) => {
                e.preventDefault();
                refs.current[i]?.scrollIntoView({ behavior: "smooth", block: "center" });
              }}
            >
              <span>{String(i + 1).padStart(2, "0")}</span>
              {w.title}
            </a>
          </li>
        ))}
      </ol>
      <div className={styles.wlStack}>
        {items.map((w, i) => (
          <section
            key={w.title}
            id={`wl-${i}`}
            data-index={i}
            ref={(el) => {
              refs.current[i] = el;
            }}
            className={styles.wlCard}
            data-active={i === active}
          >
            <div className={styles.wlCardVisual}>
              <WorkloadVisual kind={w.visual} />
            </div>
            <div className={styles.wlCardBody}>
              <h3>{w.title}</h3>
              <p>{w.body}</p>
              <ul className={styles.checks}>
                {w.points.map((p) => (
                  <li key={p}>
                    <Check aria-hidden="true" />
                    {p}
                  </li>
                ))}
              </ul>
              <code className={styles.wlCommand}>{w.api.split("\n")[0]}</code>
              <Link href={w.href} className={styles.pillGhost}>
                {w.action}
              </Link>
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

// ── C · Code tabs (Cloudflare Workers / warp.dev) ──
// One file per workload; running it prints the real response shape and a measured fact.
export function CodeTabs({ items }: { items: ReadonlyArray<Workload> }) {
  const [active, setActive] = useState(0);
  const [run, setRun] = useState(0);
  const item = items[active];
  const lines = item.output.split("\n");
  // Lines print one by one after each tab change or re-run; the key resets the count.
  const [printed, setPrinted] = useState({ key: "", count: 0 });
  const runKey = `${active}-${run}`;
  const shown = printed.key === runKey ? printed.count : 0;

  useEffect(() => {
    // Reduced motion prints everything at once on the first tick.
    const all = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let k = all ? lines.length - 1 : 0;
    const id = window.setInterval(() => {
      k += 1;
      setPrinted({ key: runKey, count: k });
      if (k >= lines.length) window.clearInterval(id);
    }, 380);
    return () => window.clearInterval(id);
  }, [runKey, lines.length]);

  return (
    <div className={styles.wlTabs}>
      <div className={styles.wlEditor}>
        <div className={styles.wlFileTabs} role="tablist" aria-label="Workloads">
          {items.map((w, i) => (
            <button key={w.file} role="tab" type="button" aria-selected={i === active} onClick={() => setActive(i)}>
              {w.file}
            </button>
          ))}
        </div>
        <pre className={styles.wlCode}>
          <code>{item.code}</code>
        </pre>
        <div className={styles.wlTerminal}>
          <div className={styles.wlTermHead}>
            <span>OUTPUT</span>
            <button type="button" onClick={() => setRun((r) => r + 1)}>
              RUN AGAIN
            </button>
          </div>
          <pre>
            <code>{lines.slice(0, shown).join("\n")}</code>
          </pre>
        </div>
      </div>
      <div className={styles.wlAside}>
        <h3>{item.title}</h3>
        <p>{item.body}</p>
        <div className={styles.wlFactBig}>{item.fact}</div>
        <span className={styles.statusTag} data-status={item.status}>
          {item.status}
        </span>
      </div>
    </div>
  );
}

// ── Variant switch for review (dev only; ?workloads=a|b|c) ──
const listeners = new Set<() => void>();
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};
type Variant = "a" | "b" | "c";
const read = (): Variant => {
  const v = new URLSearchParams(window.location.search).get("workloads");
  return v === "b" || v === "c" ? v : "a";
};

export function WorkloadsLab({ items }: { items: ReadonlyArray<Workload> }) {
  const variant = useSyncExternalStore(subscribe, read, () => "a" as Variant);
  const choose = (v: Variant) => {
    const url = new URL(window.location.href);
    url.searchParams.set("workloads", v);
    window.history.replaceState(null, "", url);
    listeners.forEach((l) => l());
  };
  return (
    <>
      {process.env.NODE_ENV !== "production" ? (
        <div className={styles.wlSwitch} role="group" aria-label="Workloads variant (dev only)">
          {(
            [
              ["a", "A · Mesh console"],
              ["b", "B · Scroll index"],
              ["c", "C · Code tabs"],
            ] as const
          ).map(([v, label]) => (
            <button key={v} type="button" aria-pressed={variant === v} onClick={() => choose(v)}>
              {label}
            </button>
          ))}
        </div>
      ) : null}
      {variant === "a" ? <MeshConsole items={items} /> : variant === "b" ? <ScrollIndex items={items} /> : <CodeTabs items={items} />}
    </>
  );
}
