# Exam Website Monitor Extension

This extension reports website names opened in other tabs during an active exam session.

## How It Works

1. Student starts exam in the web app.
2. Student exam page sends session details to the extension (submission id, API base URL, auth token).
3. Extension listens for active-tab changes and reports non-exam URLs to backend `/events/extension-site`.
4. Teacher sees entries as `external_site_opened` in live replay/stream.

## Install (Developer Mode)

1. Open Chrome/Edge extensions page (`chrome://extensions` or `edge://extensions`).
2. Enable Developer Mode.
3. Click Load unpacked.
4. Select this folder:
   - `browser-extension/website-monitor-extension`

## Notes

- The extension only reports while exam session tracking is active.
- Browser-restricted URLs (like `chrome://`) are ignored.
- If extension is not installed or not connected, student page shows "not connected".
