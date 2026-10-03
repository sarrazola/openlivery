// Extension points of the agency's inbox.
//
// The inbox reads every conversation and operates none: the client's own team
// takes and answers from the client portal. A deployment may let its people
// take and answer some conversations from here, for instance those of a client
// the deployment itself runs, by replacing this file at build time; the core
// ships it inert, and the inbox reads it through this one import.

import type { Conversation } from "@/types";

/** Whether the open conversation may be taken and answered from the inbox. */
export type UseCanOperate = (conversation: Conversation | null) => boolean;

export const inboxExtensions: {
  useCanOperate: UseCanOperate;
} = {
  useCanOperate: () => false,
};
