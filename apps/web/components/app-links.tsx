"use client";

import { ExternalLink } from "lucide-react";

// Plain links to the stores the deployment configured (PORTAL_IOS_APP_URL,
// PORTAL_ANDROID_APP_URL), shown to the agency under Settings so it can pass
// them on. Text rather than the stores' badge artwork. Store names are proper
// nouns and stay as they are in every language.
export function AppLinks({ ios, android, className }: { ios?: string | null; android?: string | null; className?: string }) {
  if (!ios && !android) return null;
  return (
    <div className={`app-links${className ? ` ${className}` : ""}`}>
      {ios && <a href={ios} target="_blank" rel="noopener noreferrer">App Store <ExternalLink size={13} /></a>}
      {android && <a href={android} target="_blank" rel="noopener noreferrer">Google Play <ExternalLink size={13} /></a>}
    </div>
  );
}
