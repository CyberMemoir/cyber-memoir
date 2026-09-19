"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  ["/", "记忆索引"],
  ["/universe", "梗的星图"],
  ["/submit", "提交来源"],
  ["/review", "审核工作台"],
] as const;

/** The current page carries aria-current, which is also what draws its marker. */
export function NavLinks() {
  const path = usePathname();
  return (
    <nav aria-label="主导航" className="site-nav">
      {LINKS.map(([href, label]) => {
        const current = href === "/" ? path === "/" : path.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={current ? "page" : undefined}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
