import Link from "next/link";
import { Icon } from "./icons";
import { NavLinks } from "./nav-links";

/** The brand mark: a two-armed spiral, the shape every meme takes on the star map. */
function Mark() {
  return (
    <svg className="brand-mark" width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
      <circle cx="15" cy="15" r="2.4" />
      <path d="M 15 12.6 C 21 11.8 24.2 16.4 22 21 C 20.6 24 17 25.6 13.2 25" />
      <path d="M 15 17.4 C 9 18.2 5.8 13.6 8 9 C 9.4 6 13 4.4 16.8 5" />
    </svg>
  );
}

export function Header() {
  return (
    <header className="site-header">
      <div className="header-inner">
        <Link href="/" className="brand" aria-label="Cyber Memoir 赛博回忆录，回到记忆索引">
          <Mark />
          <span className="brand-words">
            <span className="brand-latin">Cyber Memoir</span>
            <span className="brand-cjk">赛博回忆录</span>
          </span>
        </Link>
        <NavLinks />
        <a
          className="github"
          href="https://github.com/CyberMemoir/cyber-memoir"
          target="_blank"
          rel="noreferrer"
        >
          GitHub <Icon name="arrow" size={15} />
        </a>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="site-footer">
      <span className="footer-line">记忆会流动，证据应当留下。</span>
      <span className="footer-meta">开源 · Evidence First</span>
    </footer>
  );
}

/**
 * The archive's three rules, said once as a sentence. They are not features to
 * scan; they are what every page here is promising.
 */
export function Principles() {
  return (
    <aside className="principles">
      <h2>证据，先于结论。</h2>
      <p>
        每一条记录都尽可能链接到最早可验证的原始内容；记下它最早被看到的时间与地点，但不把这当作互联网起源；
        信息缺口和存疑之处照实标出，不替读者补全。
      </p>
    </aside>
  );
}
