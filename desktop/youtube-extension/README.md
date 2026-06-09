# X9 YouTube Creator Email Preview

Experimental Chrome MV3 extension for collecting public YouTube creator email previews from manually prepared search results.

## What it does

- Starts from the active YouTube search results page that you prepared manually.
- Opens visible video results and checks expanded video details first.
- Checks creator channel home pages, then About pages, when video details have no email.
- Keeps channel URLs with an empty `email` field when no public email is visible.
- Stores the latest preview in `chrome.storage.local`.
- Uploads completed runs to the local X9 backend by default.
- Exports JSON or CSV from the side panel.

## What it does not do

- It does not include or use a YouTube API key.
- It does not upload to `usx9.us` in the default local test mode.
- It does not bypass login, captcha, hidden email buttons, or private data.
- It does not click YouTube hidden "view email address" buttons.
- It is not wired into `/api/local/extension/download`.

## Backend mode

Upload target is configured in `youtube_config.js`.

- Default: `mode: "local"` -> `http://127.0.0.1:8000`
- Reserved for release testing: `mode: "production"` -> `https://usx9.us`

Keep local mode until the YouTube flow has passed end-to-end testing.

## Local test

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Click "Load unpacked".
4. Select `desktop/youtube-extension`.
5. Start the local backend on `http://127.0.0.1:8000` and log in.
6. Search a keyword on YouTube manually and stay on the results page.
7. Open the extension side panel and click "Start Creator Email Run".

Use the export buttons as a fallback when local upload fails.
