"use client";

// Which models this workspace can actually pick, asked from the API: the
// catalog is what OpenRouter serves right now, and a deployment may narrow it
// (to what a shared key covers, say). While loading or on error the static
// seed lists apply unchanged.

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { setLiveModels, type LiveModel } from "@/lib/providers";

export type AvailableModels = {
  chat: Record<string, string[]>;
  image: string[];
  audio: string[];
  embedding?: string[];
};

let cached: AvailableModels | null = null;
let metadataLoaded = false;

export function useAvailableModels(): AvailableModels | null {
  const [data, setData] = useState<AvailableModels | null>(cached);
  useEffect(() => {
    // Names, context windows and prices for every model on offer, so the
    // pickers can label what they list.
    if (!metadataLoaded) {
      metadataLoaded = true;
      api<LiveModel[]>("/catalog/models").then(setLiveModels).catch(() => { metadataLoaded = false; });
    }
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

/** The ids the API allows, with the ones the static seed knows first (they
 * carry curated labels and the recommended default), then everything else
 * OpenRouter serves. An unknown or empty answer keeps the static list, so the
 * UI never ends up with nothing to offer. */
export function narrowModels(list: readonly string[], allowed?: string[] | null): string[] {
  if (!allowed || !allowed.length) return [...list];
  const set = new Set(allowed);
  const known = list.filter((id) => set.has(id));
  const knownSet = new Set(known);
  return [...known, ...allowed.filter((id) => !knownSet.has(id))];
}
