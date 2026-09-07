/** The system back action follows the same destination as the visible back button. */
export function backDestination(
  screen: string,
  returnTo: "list" | "contacts",
): "list" | "contacts" | null {
  if (screen === "chat") return returnTo;
  if (screen === "contacts" || screen === "workspace") return "list";
  return null;
}
