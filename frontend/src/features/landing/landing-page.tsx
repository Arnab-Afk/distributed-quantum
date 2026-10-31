import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  BookMarked,
  ChartNoAxesColumn,
  Check,
  Coins,
  FileText,
  MonitorDot,
  Network,
  PackageCheck,
  Plus,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { Inter, Newsreader } from "next/font/google";

import { ArchStack } from "./components/arch-stack";
import { InfrastructureStrip } from "./components/infrastructure-strip";
import { Identicon, MeshMark } from "./components/mesh-mark";
import { GlyphBand, HeroMesh, InkWordmark, ResultsStory, Reveal, RollingNumber } from "./components/motion-bits";
import { SmoothScroll } from "./components/smooth-scroll";
import { ReceiptScroll } from "./components/receipt-scroll";
import { WorkloadIndex } from "./components/workloads";
import {
  ARCHITECTURE,
  CLOSING,
  CONSOLE_HREF,
  DEMO_URL,
  DEVELOPERS,
  FAQ,
  FOOTER,
  GLYPHS,
  HERO,
  NAV,
  PRODUCTS,
  RECEIPT,
  REPOSITORY_URL,
  RESEARCH_URL,
  RESULTS,
  TEAM,
  WORKLOADS,
} from "./landing-content";
import styles from "./landing.module.css";

const display = Newsreader({
  subsets: ["latin"],
  weight: ["300", "400"],
  style: ["normal", "italic"],
  variable: "--landing-display",
});
const text = Inter({ subsets: ["latin"], weight: ["300", "400", "500", "600"], variable: "--landing-text" });

const ICONS: Record<(typeof PRODUCTS.groups)[number]["items"][number]["icon"], LucideIcon> = {
  console: MonitorDot,
  coordinator: Workflow,
  peer: Network,
  registry: BookMarked,
  payment: Coins,
  bundle: PackageCheck,
  benchmark: ChartNoAxesColumn,
  paper: FileText,
};

function External({ href, className, children }: { href: string; className?: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className={className}>
      {children}
    </a>
  );
}

export function LandingPage() {
  return (
    <div id="top" className={`${styles.page} ${display.variable} ${text.variable}`}>
      <SmoothScroll />
      <div className={styles.rails} aria-hidden="true" />

      <header className={styles.nav}>
        <Link href="/" className={styles.brand} aria-label="QMesh home">
          <MeshMark className={styles.brandMark} />
          <span>QMesh</span>
        </Link>
        <nav className={styles.navLinks} aria-label="Sections">
          {NAV.links.map((link) => (
            <a key={link.href} href={link.href}>
              {link.label}
            </a>
          ))}
        </nav>
        <div className={styles.navActions}>
          <External href={REPOSITORY_URL} className={styles.pillText}>
            {NAV.secondary}
          </External>
          <Link href={CONSOLE_HREF} className={styles.pill}>
            {NAV.primary}
          </Link>
        </div>
      </header>

      <main>
        <section className={styles.hero} aria-labelledby="hero-title">
          <div className={styles.heroIntro}>
            <h1 id="hero-title" className={styles.h1}>
              {HERO.title[0]}
              <br />
              <em>{HERO.title[1]}</em>
            </h1>
            <p className={styles.heroLead}>
              {HERO.body} <span>{HERO.muted}</span>
            </p>
            <div className={styles.actions}>
              <External href={DEMO_URL} className={styles.pill}>
                {HERO.primary} <ArrowRight aria-hidden="true" />
              </External>
              <Link href={CONSOLE_HREF} className={styles.pillGhost}>
                {HERO.secondary}
              </Link>
            </div>
          </div>
          <HeroMesh label={HERO.scene} caption={HERO.sceneCaption} />
          <a href="#architecture" className={styles.ribbon}>
            <span className={styles.ribbonDot} aria-hidden="true" />
            {HERO.ribbon} <ArrowRight aria-hidden="true" />
          </a>
        </section>

        <GlyphBand label={GLYPHS.label} />

        <InfrastructureStrip />

        <section id="architecture" className={styles.architecture} aria-labelledby="architecture-title">
          <ArchStack title={ARCHITECTURE.title} body={ARCHITECTURE.body} layers={ARCHITECTURE.layers} />
        </section>

        <section id="workloads" className={styles.section} aria-labelledby="workloads-title">
          <Reveal>
            <h2 id="workloads-title" className={styles.h2}>
              {WORKLOADS.title}
            </h2>
          </Reveal>
          <WorkloadIndex items={WORKLOADS.items} />
        </section>

        <section className={styles.section} aria-labelledby="products-title">
          <h2 id="products-title" className={styles.h2Sans}>
            {PRODUCTS.title}
          </h2>
          <div className={styles.products}>
            {PRODUCTS.groups.map((group) => (
              <div key={group.title} className={styles.productGroup}>
                <h3 className={styles.productGroupTitle}>{group.title}</h3>
                <ul>
                  {group.items.map((item) => {
                    const Icon = ICONS[item.icon];
                    return (
                      <li key={item.title} className={styles.product}>
                        <span className={styles.productIcon}>
                          <Icon aria-hidden="true" />
                        </span>
                        <span>
                          <strong>{item.title}</strong>
                          <small>{item.body}</small>
                        </span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </section>

        <section id="results" className={styles.section} aria-labelledby="results-title">
          <div className={styles.sectionHead}>
            <h2 id="results-title" className={styles.h2}>
              {RESULTS.title}
            </h2>
            <External href={DEMO_URL} className={styles.pillGhost}>
              {RESULTS.action} <ArrowRight aria-hidden="true" />
            </External>
          </div>
          <ResultsStory story={RESULTS.story} paperHref={RESEARCH_URL} />
          <dl className={styles.stats}>
            {RESULTS.stats.map((stat) => (
              <div key={stat.title} className={styles.stat}>
                <dt className={styles.statValue}>
                  <RollingNumber value={stat.value} suffix={stat.suffix} />
                </dt>
                <dd>
                  <span className={styles.statTitle}>{stat.title}</span>
                  {stat.body}
                </dd>
              </div>
            ))}
          </dl>
          <p className={styles.footnote}>{RESULTS.footnote}</p>
        </section>

        <section id="receipt" className={styles.section} aria-labelledby="receipt-title">
          <ReceiptScroll receipt={RECEIPT} />
        </section>

        <section id="developers" className={styles.section} aria-labelledby="developers-title">
          <div className={styles.developers}>
            <div className={styles.devIntro}>
              <h2 id="developers-title" className={styles.h2Sans}>
                {DEVELOPERS.title}
              </h2>
              <p className={styles.devSubtitle}>{DEVELOPERS.subtitle}</p>
              <ul className={styles.devChecks}>
                {DEVELOPERS.checks.map((check) => (
                  <li key={check.title}>
                    <Check aria-hidden="true" />
                    <span>
                      <strong>{check.title}</strong>
                      {check.body}
                    </span>
                  </li>
                ))}
              </ul>
              <div className={styles.actions}>
                <Link href={CONSOLE_HREF} className={styles.pill}>
                  {DEVELOPERS.primary} <ArrowRight aria-hidden="true" />
                </Link>
                <External href={REPOSITORY_URL} className={styles.pillGhost}>
                  {DEVELOPERS.secondary}
                </External>
              </div>
            </div>
            <div className={styles.codePanel}>
              <div className={styles.codeCard}>
                <span className={styles.codeLabel}>{"// Request"}</span>
                <pre>
                  <code>{DEVELOPERS.request}</code>
                </pre>
                <span className={styles.codeLabel}>{"// Challenge"}</span>
                <pre>
                  <code>{DEVELOPERS.challenge}</code>
                </pre>
                <span className={styles.codeLabel}>{"// Response, once paid"}</span>
                <pre>
                  <code>{DEVELOPERS.response}</code>
                </pre>
              </div>
            </div>
          </div>
          <div className={styles.linkCards}>
            {DEVELOPERS.cards.map((card) => (
              <External key={card.title} href={card.href} className={styles.linkCard}>
                <span className={styles.linkCardTitle}>
                  {card.title} <ArrowUpRight aria-hidden="true" />
                </span>
                <span>{card.body}</span>
              </External>
            ))}
          </div>
        </section>

        <section id="team" className={styles.section} aria-labelledby="team-title">
          <div className={styles.sectionHead}>
            <h2 id="team-title" className={styles.h2}>
              {TEAM.title}
            </h2>
            <p className={styles.lead}>{TEAM.body}</p>
          </div>
          <ul className={styles.team}>
            {TEAM.members.map((member) => (
              <li key={member.name} className={styles.member}>
                <Identicon seed={member.name} />
                <span className={styles.memberName}>{member.name}</span>
                <span className={styles.memberRole}>{member.role}</span>
                {member.github ? (
                  <External href={`https://github.com/${member.github}`} className={styles.memberLink}>
                    @{member.github} <ArrowUpRight aria-hidden="true" />
                  </External>
                ) : null}
              </li>
            ))}
          </ul>
        </section>

        <section id="faq" className={`${styles.section} ${styles.faq}`} aria-labelledby="faq-title">
          <h2 id="faq-title" className={styles.h2}>
            {FAQ.title}
          </h2>
          <div className={styles.faqList}>
            {FAQ.items.map((item, index) => (
              <details key={item.question} className={styles.faqItem} open={index === 0}>
                <summary>
                  {item.question}
                  <Plus aria-hidden="true" className={styles.faqIcon} />
                </summary>
                <p>{item.answer}</p>
              </details>
            ))}
          </div>
        </section>

      </main>

      <footer className={styles.footer}>
        <div className={styles.footerTop}>
          <div className={styles.footerCta}>
            <h2 id="closing-title" className={styles.footerHeading}>
              {CLOSING.title}
            </h2>
            <Link href={CONSOLE_HREF} className={styles.pill}>
              {CLOSING.primary} <ArrowRight aria-hidden="true" />
            </Link>
          </div>
          <div className={styles.inkFrame}>
            <InkWordmark word={FOOTER.wordmark} />
          </div>
        </div>
        <div className={styles.footerBottom}>
          <div className={styles.footerNote}>
            <span className={styles.brand}>
              <MeshMark className={styles.brandMark} />
              <span>QMesh</span>
            </span>
            <p>{FOOTER.blurb}</p>
            <p className={styles.footerScope}>{FOOTER.scope}</p>
          </div>
          {FOOTER.columns.map((column) => (
            <div key={column.title} className={styles.footerColumn}>
              <h3>{column.title}</h3>
              <ul>
                {column.links.map((link) => (
                  <li key={link.label}>
                    {link.href.startsWith("http") ? (
                      <External href={link.href}>{link.label}</External>
                    ) : (
                      <Link href={link.href}>{link.label}</Link>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className={styles.footerMeta}>{FOOTER.copy}</p>
      </footer>
    </div>
  );
}
