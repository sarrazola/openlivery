import type { TranslateFn } from "@/lib/i18n";
import type { Message } from "@/types";

// The one place that turns an activity event (resolved, assigned, routed by
// tag...) into a sentence, shared by the inbox thread and read-only views.
export function activityText(t: TranslateFn, message: Message): string {
  const actor = message.sender_name || t("portal.inbox.activity.someone");
  const details = message.activity;
  switch (details?.event) {
    case "resolved": return t("portal.inbox.activity.resolved", { actor });
    case "archived": return t("portal.inbox.activity.archived", { actor });
    case "blocked": return t("portal.inbox.activity.blocked", { actor });
    case "unblocked": return t("portal.inbox.activity.unblocked", { actor });
    case "unarchived": return t("portal.inbox.activity.unarchived", { actor });
    case "reopened": return t("portal.inbox.activity.reopened", { actor });
    case "reopened_by_contact": return t("portal.inbox.activity.reopened_by_contact");
    case "taken_over": return t("portal.inbox.activity.taken_over", { actor });
    case "returned_to_ai": return t("portal.inbox.activity.returned_to_ai", { actor });
    case "auto_resolved": return t("portal.inbox.activity.auto_resolved", { hours: String(details?.hours ?? "") });
    case "self_assigned": return t("portal.inbox.activity.self_assigned", { actor });
    case "assigned": return t("portal.inbox.activity.assigned", { actor, assignee: String(details?.assignee ?? "") });
    case "transferred": return t("portal.inbox.activity.transferred", { actor, assignee: String(details?.assignee ?? "") });
    case "unassigned": return t("portal.inbox.activity.unassigned", { actor });
    case "team_assigned": return t("portal.inbox.activity.team_assigned", { actor, team: String(details?.team ?? "") });
    case "team_removed": return t("portal.inbox.activity.team_removed", { actor, team: String(details?.team ?? "") });
    case "escalated": return t("portal.inbox.activity.escalated", { actor, target: String(details?.target ?? ""), reason: String(details?.reason ?? "") });
    case "routed_by_tag": return t("portal.inbox.activity.routed_by_tag", { target: String(details?.target ?? ""), tag: String(details?.tag ?? "") });
    default: return message.content;
  }
}
