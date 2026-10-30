"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { Check } from "lucide-react";
import { useState } from "react";

import type { Workload } from "../landing-content";
import styles from "../landing.module.css";

const EASE = [0.16, 1, 0.3, 1] as const;

/** Accordion of workloads beside a capture with a live-looking result card (UI) or its request (API). */
export function WorkloadSwitcher({ items }: { items: ReadonlyArray<Workload> }) {
  const [active, setActive] = useState(0);
  const [view, setView] = useState<"ui" | "api">("ui");
  const item = items[active];

  return (
    <div className={styles.workloads}>
      <ul className={styles.workloadList}>
        {items.map((w, i) => {
          const open = i === active;
          return (
            <li key={w.title} data-open={open}>
              <button
                type="button"
                className={styles.workloadToggle}
                aria-expanded={open}
                aria-controls={`workload-${i}`}
                onClick={() => setActive(i)}
              >
                {w.title}
              </button>
              <div id={`workload-${i}`} className={styles.workloadBody} hidden={!open}>
                <p>{w.body}</p>
                <ul className={styles.checks}>
                  {w.points.map((point) => (
                    <li key={point}>
                      <Check aria-hidden="true" />
                      {point}
                    </li>
                  ))}
                </ul>
                <div className={styles.workloadFoot}>
                  <Link href={w.href} className={styles.pillGhost}>
                    {w.action}
                  </Link>
                  <span className={styles.statusTag} data-status={w.status}>
                    {w.status}
                  </span>
                </div>
              </div>
            </li>
          );
        })}
      </ul>

      <div className={styles.workloadPanel}>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={`${item.title}-${view}`}
            className={styles.resultCard}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.45, ease: EASE }}
          >
            {view === "ui" ? (
              <>
                <div className={styles.resultHead}>
                  <span>
                    {item.card.label}
                    <small>{item.card.meta}</small>
                  </span>
                  <span className={styles.resultBadge}>{item.status}</span>
                </div>
                <span className={styles.resultLabel}>{item.card.headlineLabel}</span>
                <strong className={styles.resultValue}>{item.card.headline}</strong>
                <dl className={styles.resultRows}>
                  {item.card.rows.map(([label, value]) => (
                    <div key={label}>
                      <dt>{label}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
                </dl>
              </>
            ) : (
              <pre className={styles.resultCode}>
                <code>{item.api}</code>
              </pre>
            )}
          </motion.div>
        </AnimatePresence>
        <div className={styles.viewToggle} role="group" aria-label="Show the result or the request">
          {(["ui", "api"] as const).map((v) => (
            <button key={v} type="button" aria-pressed={view === v} onClick={() => setView(v)}>
              {v.toUpperCase()}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
