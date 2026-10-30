"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { PhoneModel } from "@/types";

/** The models a voice agent thinks with, all run by ElevenLabs next to the
 * voice; the first is the default. */
export function VoiceModelPicker({ value, onChange }: { value: string; onChange: (model: string) => void }) {
  const [models, setModels] = useState<PhoneModel[]>([]);
  useEffect(() => { api<PhoneModel[]>("/phone/models").then(setModels).catch(() => setModels([])); }, []);
  const known = models.some((model) => model.id === value);
  return <select value={value} onChange={(event) => onChange(event.target.value)}>
    {!known && <option value={value} disabled>{value || "…"}</option>}
    {models.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}
  </select>;
}
