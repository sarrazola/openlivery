(function () {
  var script = document.currentScript;
  if (!script) return;
  var agent = script.getAttribute("data-agent");
  if (!agent) return;
  var origin = new URL(script.src).origin;
  var color = script.getAttribute("data-color") || "#635bff";
  var side = script.getAttribute("data-position") === "left" ? "left" : "right";
  var open = false;
  var teaserShown = false;
  var unread = 0;

  var frame = document.createElement("iframe");
  frame.src = origin + "/widget/" + encodeURIComponent(agent);
  frame.title = "Chat";
  frame.setAttribute("allow", "clipboard-write; microphone");
  frame.style.cssText =
    "position:fixed;bottom:92px;" + side + ":20px;width:380px;max-width:calc(100vw - 40px);" +
    "height:600px;max-height:calc(100vh - 120px);border:0;border-radius:16px;z-index:2147483000;" +
    "box-shadow:0 18px 48px rgba(15,23,42,.24);display:none;background:transparent;";

  var button = document.createElement("button");
  button.setAttribute("aria-label", "Chat");
  button.style.cssText =
    "position:fixed;bottom:20px;" + side + ":20px;width:56px;height:56px;border:0;border-radius:50%;" +
    "cursor:pointer;z-index:2147483000;background:" + color + ";color:#fff;display:flex;" +
    "align-items:center;justify-content:center;box-shadow:0 10px 26px rgba(15,23,42,.28);";
  button.innerHTML =
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>';

  // Unread counter on the launcher (shown when replies arrive while closed).
  var badge = document.createElement("span");
  badge.style.cssText =
    "position:absolute;top:-4px;" + (side === "left" ? "left" : "right") + ":-4px;min-width:20px;height:20px;" +
    "padding:0 5px;border-radius:10px;background:#ef4444;color:#fff;font:700 12px/20px -apple-system,system-ui,sans-serif;" +
    "text-align:center;box-shadow:0 0 0 2px #fff;display:none;box-sizing:border-box;";
  button.appendChild(badge);

  function setUnread(n) {
    unread = n;
    if (unread > 0) { badge.textContent = unread > 9 ? "9+" : String(unread); badge.style.display = "block"; }
    else badge.style.display = "none";
  }

  // Greeting teaser bubble next to the launcher (dismissable).
  var teaser = document.createElement("div");
  teaser.style.cssText =
    "position:fixed;bottom:86px;" + side + ":20px;max-width:260px;padding:12px 32px 12px 14px;" +
    "background:#fff;color:#1f2937;border-radius:14px;border-bottom-" + side + "-radius:4px;" +
    "font:400 14px/1.45 -apple-system,system-ui,sans-serif;box-shadow:0 12px 30px rgba(15,23,42,.18);" +
    "z-index:2147482999;cursor:pointer;display:none;";
  var teaserClose = document.createElement("span");
  teaserClose.textContent = "×";
  teaserClose.style.cssText =
    "position:absolute;top:6px;right:9px;color:#9ca3af;font-size:16px;line-height:1;cursor:pointer;";
  teaser.appendChild(teaserClose);
  var teaserText = document.createElement("span");
  teaser.appendChild(teaserText);

  function post(action) {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars -- the frame may not be ready; nothing to do
    try { if (frame.contentWindow) frame.contentWindow.postMessage({ type: "ol-widget-host", action: action }, origin); } catch (err) {}
  }
  function hideTeaser() { teaser.style.display = "none"; }
  function setOpen(next) {
    open = next;
    frame.style.display = open ? "block" : "none";
    if (open) { setUnread(0); hideTeaser(); }
    post(open ? "opened" : "closed");
  }

  button.addEventListener("click", function () { setOpen(!open); });
  teaser.addEventListener("click", function () { setOpen(true); });
  teaserClose.addEventListener("click", function (e) { e.stopPropagation(); hideTeaser(); teaserShown = true; });

  window.addEventListener("message", function (event) {
    if (event.origin !== origin || !event.data || event.data.type !== "ol-widget") return;
    var d = event.data;
    if (d.action === "close") setOpen(false);
    if (d.action === "greeting" && !open && !teaserShown && d.text) {
      teaserText.textContent = String(d.text).slice(0, 220);
      teaser.style.display = "block";
      teaserShown = true;
    }
    if (d.action === "unread" && !open) setUnread(unread + 1);
  });

  document.body.appendChild(frame);
  document.body.appendChild(button);
  document.body.appendChild(teaser);
})();
