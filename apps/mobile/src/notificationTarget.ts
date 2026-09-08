import { notificationData } from "./notificationData";

/** A push selects a record, never a server or authentication identity. */
export function notificationTarget(value: unknown, clientId: string): string | null {
  const data = notificationData(value);
  if (typeof data.conversation_id !== "string" || !data.conversation_id.trim() || data.conversation_id.length > 128) return null;
  if (data.client_id !== undefined && data.client_id !== clientId) return null;
  return data.conversation_id;
}
