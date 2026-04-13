let activeSession = null;
const recentUrlHits = new Map();

const EXCLUDED_PROTOCOLS = ["chrome:", "edge:", "about:", "devtools:", "chrome-extension:"];
const EXAM_PAGE_PATTERNS = [
  "http://localhost:5173/*",
  "http://127.0.0.1:5173/*",
  "http://localhost:5174/*",
  "http://127.0.0.1:5174/*",
  "https://*.trycloudflare.com/*",
  "https://*.ngrok-free.dev/*",
  "https://*.ngrok.app/*",
];

function isInjectableWebUrl(url) {
  if (!url) {
    return false;
  }
  return /^https?:\/\//i.test(url);
}

async function injectBridgeIntoTab(tabId) {
  if (!tabId) {
    return;
  }
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content-bridge.js"],
    });
  } catch {
    // Ignore tabs where script cannot be injected.
  }
}

async function injectBridgeIntoExamTabs() {
  try {
    const tabs = await chrome.tabs.query({ url: EXAM_PAGE_PATTERNS });
    await Promise.all(
      tabs.map(async (tab) => {
        if (!tab?.id || !isInjectableWebUrl(tab.url)) {
          return;
        }
        await injectBridgeIntoTab(tab.id);
      })
    );
  } catch {
    // Keep extension resilient if query/injection fails.
  }
}

function isExcludedUrl(url) {
  if (!url) {
    return true;
  }
  return EXCLUDED_PROTOCOLS.some((prefix) => url.startsWith(prefix));
}

chrome.runtime.onInstalled.addListener(() => {
  injectBridgeIntoExamTabs();
});

chrome.runtime.onStartup.addListener(() => {
  injectBridgeIntoExamTabs();
});

function toHostname(url) {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function isExamOrigin(url) {
  if (!activeSession?.examOrigin || !url) {
    return false;
  }
  return url.startsWith(activeSession.examOrigin);
}

function shouldReportUrl(url) {
  if (!activeSession || !url) {
    return false;
  }
  if (isExcludedUrl(url)) {
    return false;
  }
  if (isExamOrigin(url)) {
    return false;
  }

  const now = Date.now();
  const lastTs = recentUrlHits.get(url) || 0;
  if (now - lastTs < 8000) {
    return false;
  }
  recentUrlHits.set(url, now);
  return true;
}

async function postSiteEvent(tab, trigger) {
  const url = tab?.url;
  if (!shouldReportUrl(url)) {
    return;
  }

  const startedAtMs = Number(activeSession.startedAtMs || Date.now());
  const timestampMs = Math.max(0, Date.now() - startedAtMs);
  const payload = {
    submission_id: Number(activeSession.submissionId),
    url,
    title: String(tab?.title || ""),
    hostname: toHostname(url),
    trigger,
    timestamp_ms: timestampMs,
  };

  try {
    await fetch(`${activeSession.apiBaseUrl}/events/extension-site`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${activeSession.token}`,
      },
      body: JSON.stringify(payload),
    });
  } catch {
    // Keep extension silent when backend is unreachable.
  }
}

chrome.runtime.onMessage.addListener((message) => {
  if (message?.source !== "exam-proctor-app") {
    return;
  }

  if (message.type === "EXTENSION_TRACKING_START") {
    const payload = message.payload || {};
    if (!payload.submissionId || !payload.token || !payload.apiBaseUrl) {
      return;
    }

    let resolvedApiBaseUrl = String(payload.apiBaseUrl);
    try {
      resolvedApiBaseUrl = new URL(String(payload.apiBaseUrl), String(payload.examOrigin || undefined)).toString();
    } catch {
      // Keep original value if URL construction fails.
    }

    activeSession = {
      submissionId: Number(payload.submissionId),
      startedAtMs: Number(payload.startedAtMs || Date.now()),
      token: String(payload.token),
      apiBaseUrl: resolvedApiBaseUrl.replace(/\/$/, ""),
      examOrigin: String(payload.examOrigin || ""),
    };
    return;
  }

  if (message.type === "EXTENSION_TRACKING_STOP") {
    activeSession = null;
    recentUrlHits.clear();
  }
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  if (!activeSession) {
    return;
  }
  try {
    const tab = await chrome.tabs.get(tabId);
    await postSiteEvent(tab, "tab_activated");
  } catch {
    // no-op
  }
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && isInjectableWebUrl(tab?.url || "")) {
    await injectBridgeIntoTab(tabId);
  }

  if (!activeSession || changeInfo.status !== "complete") {
    return;
  }
  if (!tab?.active) {
    return;
  }
  await postSiteEvent(tab, "tab_updated");
});
