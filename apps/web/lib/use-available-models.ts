"use client";

// Which models this workspace can actually pick, asked from the API so a
// deployment can narrow the offer (a stock install returns the full catalog).
// While loading or on error the static lists apply unchanged.

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export type AvailableModels = {
  chat: Record<string, string[]>;
  image: string[];
  audio: string[];
};

let cached: AvailableModels | null = null;

export function useAvailableModels(): AvailableModels | null {
  const [data, setData] = useState<AvailableModels | null>(cached);
  useEffect(() => {
    if (cached) return;
    api<AvailableModels>("/catalog/available")
      .then((payload) => {
        cached = payload;
        setData(payload);
      })
      .catch(() => {});
  }, []);
  return data;
}

/** Intersect a static list with the allowed ids; an unknown or empty answer
 * keeps the full list, so the UI never ends up with nothing to offer. */
export function narrowModels(list: readonly string[], allowed?: string[] | null): string[] {
  if (!allowed || !allowed.length) return [...list];
  const set = new Set(allowed);
  const kept = list.filter((id) => set.has(id));
  return kept.length ? kept : [...list];
}
