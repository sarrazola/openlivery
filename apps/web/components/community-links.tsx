"use client";

import { useEffect, useState } from "react";
import { Star } from "lucide-react";
import { useT } from "@/lib/i18n";
import { DiscordIcon } from "@/components/discord-icon";
import { GithubIcon } from "@/components/github-icon";
import { COMMUNITY_LINKS, DISCORD_INVITE_URL, GITHUB_REPO, GITHUB_REPO_URL } from "@/lib/community";

const STARS_CACHE_KEY = `openlivery:github-stars:${GITHUB_REPO}`;
const STARS_TTL_MS = 60 * 60 * 1000;

// GitHub's public API allows 60 unauthenticated calls per hour per address, so
// the count is cached in sessionStorage for an hour and any failure just hides
// the badge.
function useGithubStars(enabled: boolean): number | null {
  const [stars, setStars] = useState<number | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    try {
      const cached = sessionStorage.getItem(STARS_CACHE_KEY);
      if (cached) {
        const { count, at } = JSON.parse(cached) as { count: number; at: number };
        if (Date.now() - at < STARS_TTL_MS) {
          setStars(count);
          return;
        }
      }
    } catch {
      // storage unavailable: fall through to the network
    }
    fetch(`https://api.github.com/repos/${GITHUB_REPO}`, { headers: { Accept: "application/vnd.github+json" } })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { stargazers_count?: number } | null) => {
        if (cancelled || typeof data?.stargazers_count !== "number") return;
        setStars(data.stargazers_count);
        try {
          sessionStorage.setItem(STARS_CACHE_KEY, JSON.stringify({ count: data.stargazers_count, at: Date.now() }));
        } catch {
          // storage unavailable: the badge still renders for this page
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [enabled]);
  return stars;
}

function formatStars(count: number): string {
  if (count < 1000) return String(count);
  const compact = count / 1000;
  return `${compact < 10 ? compact.toFixed(1).replace(/\.0$/, "") : Math.round(compact)}k`;
}

export function CommunityLinks({ onNavigate }: { onNavigate?: () => void }) {
  const t = useT();
  const showGithub = COMMUNITY_LINKS.includes("github");
  const showDiscord = COMMUNITY_LINKS.includes("discord");
  const stars = useGithubStars(showGithub);
  if (!showGithub && !showDiscord) return null;
  return (
    <div className="sidebar-community-row">
      {showDiscord && (
        <a
          href={DISCORD_INVITE_URL}
          className="sidebar-community sidebar-community-discord"
          target="_blank"
          rel="noopener noreferrer"
          title={t("shell.joinDiscord")}
          aria-label={t("shell.joinDiscord")}
          onClick={onNavigate}
        >
          <DiscordIcon size={20} />
        </a>
      )}
      {showGithub && (
        <a
          href={GITHUB_REPO_URL}
          className="sidebar-community sidebar-community-github"
          target="_blank"
          rel="noopener noreferrer"
          title={t("shell.starOnGithub")}
          aria-label={t("shell.starOnGithub")}
          onClick={onNavigate}
        >
          <GithubIcon size={20} />
          {stars !== null && (
            <span className="sidebar-community-stars"><Star size={12} /><span>{formatStars(stars)}</span></span>
          )}
        </a>
      )}
    </div>
  );
}
