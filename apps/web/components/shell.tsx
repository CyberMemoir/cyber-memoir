import Link from "next/link";
import { Icon } from "./icons";

export function Header() {
  return (
    <header className="site-header">
      <div className="header-inner">
        <Link href="/" className="brand">
          Cyber Memoir<span>赛博回忆录</span>
        </Link>
        <nav aria-label="主导航">
          <Link href="/">记忆索引</Link>
          <Link href="/submit">提交来源</Link>
          <Link href="/review">审核工作台</Link>
        </nav>
        <a
          className="github"
          href="https://github.com/CyberMemoir/cyber-memoir"
          target="_blank"
          rel="noreferrer"
        >
          GitHub <Icon name="arrow" size={17} />
        </a>
      </div>
    </header>
  );
}
export function Footer() {
  return (
    <footer className="site-footer">
      <span>记忆会流动，证据应当留下。</span>
      <span>开源 · Evidence First</span>
    </footer>
  );
}
export function Principles() {
  return (
    <aside className="principles">
      <h2>证据，先于结论。</h2>
      <ol>
        {[
          ["保留原始出处", "尽可能链接到最早可验证的原始内容。"],
          [
            "区分记录与起源",
            "记录最早被看到的时间与地点，不等同于互联网起源。",
          ],
          ["让不确定性可见", "标注信息缺口与存疑点，避免过度确定的叙述。"],
        ].map(([title, text], i) => (
          <li key={title}>
            <span className="principle-number">0{i + 1}</span>
            <div>
              <h3>{title}</h3>
              <p>{text}</p>
            </div>
          </li>
        ))}
      </ol>
      <p className="principle-note">
        <Icon name="info" size={19} />
        <span>目前可验证的最早记录，不等于互联网起源。</span>
      </p>
    </aside>
  );
}
