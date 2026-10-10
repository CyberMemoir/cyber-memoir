"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Meme } from "@/lib/api";
import { evidenceIndex } from "@/lib/citations";

export function useReferenceNavigation(meme: Meme | null) {
  const index = useMemo(() => evidenceIndex(meme), [meme]);
  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState("");
  const [location, setLocation] = useState({
    anchor: "",
    expected: null as string | null,
    invalid: false,
    sequence: 0,
  });
  const pending = useRef(false);

  const readLocation = useCallback(() => {
    let anchor = "",
      invalid = false;
    try {
      anchor = decodeURIComponent(window.location.hash.slice(1));
    } catch {
      invalid = true;
    }
    pending.current = true;
    setLocation((old) => ({
      anchor,
      invalid,
      expected: new URLSearchParams(window.location.search).get(
        "expected_revision",
      ),
      sequence: old.sequence + 1,
    }));
    if (anchor.startsWith("evidence-") && index.has(anchor.slice(9))) {
      setQuery("");
      setPlatform("");
    }
  }, [index]);

  useEffect(() => {
    readLocation();
    window.addEventListener("hashchange", readLocation);
    window.addEventListener("popstate", readLocation);
    return () => {
      window.removeEventListener("hashchange", readLocation);
      window.removeEventListener("popstate", readLocation);
    };
    // The handlers refer to this exact public snapshot, not an old page's IDs.
  }, [readLocation]);

  useEffect(() => {
    if (!meme || !pending.current || !location.anchor || location.invalid)
      return;
    const element = document.getElementById(location.anchor);
    if (!element) return;
    let ancestor = element.closest("details");
    while (ancestor) {
      ancestor.open = true;
      ancestor = ancestor.parentElement?.closest("details") || null;
    }
    element.focus({ preventScroll: true });
    element.scrollIntoView({ block: "start", behavior: "instant" });
    pending.current = false;
  }, [meme, location, query, platform]);

  function navigate(anchor: string) {
    const url = new URL(window.location.href);
    url.hash = anchor;
    if (url.href !== window.location.href)
      window.history.pushState(null, "", url);
    readLocation();
  }

  const messages: string[] = [];
  if (meme) {
    if (location.invalid)
      messages.push("引用定位格式无效；当前展示的是公开档案。");
    if (location.expected !== null) {
      const expected = Number(location.expected);
      if (
        !/^[1-9]\d*$/.test(location.expected) ||
        !Number.isSafeInteger(expected)
      )
        messages.push("引用版本参数无效；当前展示的是公开档案。");
      else if (expected !== meme.published_revision)
        messages.push(
          `链接记录的是修订 ${expected}，当前公开修订为 ${meme.published_revision}。当前页面不是旧版本快照。`,
        );
    }
    if (
      location.anchor.startsWith("evidence-") &&
      !index.has(location.anchor.slice(9))
    )
      messages.push(
        "当前公开修订不包含这条证据，不能据此判断是版本变化还是材料撤回；请核对当前引用。",
      );
  }
  const normalized = query.trim().normalize("NFKC").toLocaleLowerCase("zh-CN");
  const visible = Array.from(index.values()).filter(
    ({ evidence }) =>
      (!platform || evidence.source?.platform === platform) &&
      (!normalized ||
        `${evidence.text}\n${evidence.source?.title || ""}\n${evidence.source?.canonical_url || ""}`
          .normalize("NFKC")
          .toLocaleLowerCase("zh-CN")
          .includes(normalized)),
  );
  return {
    index,
    query,
    setQuery,
    platform,
    setPlatform,
    visible,
    navigate,
    messages,
    activeEvidence: location.anchor.startsWith("evidence-")
      ? location.anchor.slice(9)
      : null,
  };
}
