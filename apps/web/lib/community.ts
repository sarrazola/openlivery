export const WHATSAPP_GROUP_URL = "https://chat.whatsapp.com/ECvFuV19o07IHxh94dvskZ";
export const DISCORD_INVITE_URL = "https://discord.gg/DAVJgXEdTg";
export const GITHUB_REPO = "sarrazola/openlivery";
export const GITHUB_REPO_URL = `https://github.com/${GITHUB_REPO}`;

export type CommunityLink = "whatsapp" | "discord" | "github";

// Which community logos the sidebar shows (comma-separated, baked at build).
// Unset shows all of them; `none` hides the row. Lets a deployment drop the links
// without patching the shell.
export const COMMUNITY_LINKS: CommunityLink[] = (() => {
  const raw = (process.env.NEXT_PUBLIC_COMMUNITY_LINKS || "").trim();
  if (!raw) return ["whatsapp", "discord", "github"];
  return raw
    .split(",")
    .map((entry) => entry.trim().toLowerCase())
    .filter((entry): entry is CommunityLink => entry === "whatsapp" || entry === "discord" || entry === "github");
})();
