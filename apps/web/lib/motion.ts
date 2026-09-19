"use client";
import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(onChange: () => void) {
  const media = window.matchMedia(QUERY);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

/**
 * Whether the reader asked for less motion. Decorative loops (the rotating sky,
 * twinkles, meteors, the dust drifting along a galaxy's arm) are not rendered at all
 * under it; state changes keep their colour and opacity cues. The server renders as
 * if motion were reduced, so nothing animated flashes before hydration decides.
 */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia(QUERY).matches,
    () => true,
  );
}

/**
 * Run a state change inside a view transition where the browser has one, so moving
 * from the universe into a galaxy reads as flying in rather than as a page swap.
 * Without the API, or under reduced motion, the change simply happens.
 */
export function withTransition(change: () => void, reduced: boolean): void {
  const doc = document as Document & {
    startViewTransition?: (callback: () => void) => unknown;
  };
  if (reduced || typeof doc.startViewTransition !== "function") {
    change();
    return;
  }
  doc.startViewTransition(change);
}
