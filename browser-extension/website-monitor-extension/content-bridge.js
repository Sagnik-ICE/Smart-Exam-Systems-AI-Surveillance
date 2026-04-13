(function () {
  if (window.__examProctorBridgeLoaded) {
    window.postMessage({ source: "exam-proctor-extension", type: "READY" }, "*");
    return;
  }
  window.__examProctorBridgeLoaded = true;

  const APP_SOURCE = "exam-proctor-app";
  const EXT_SOURCE = "exam-proctor-extension";

  window.postMessage({ source: EXT_SOURCE, type: "READY" }, "*");

  window.addEventListener("message", (event) => {
    if (event.source !== window) {
      return;
    }
    const message = event.data || {};
    if (message.source !== APP_SOURCE) {
      return;
    }

    if (
      message.type === "EXTENSION_TRACKING_START" ||
      message.type === "EXTENSION_TRACKING_STOP" ||
      message.type === "EXTENSION_PING"
    ) {
      window.postMessage({ source: EXT_SOURCE, type: "READY" }, "*");
      if (message.type !== "EXTENSION_PING") {
        chrome.runtime.sendMessage(message);
      }
    }
  });
})();
