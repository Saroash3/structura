"use client";

import { useSyncExternalStore } from "react";

const noop = () => () => {};

/** False during server render and hydration, true afterwards. Use for locale/time-dependent text. */
export function useMounted(): boolean {
  return useSyncExternalStore(noop, () => true, () => false);
}
