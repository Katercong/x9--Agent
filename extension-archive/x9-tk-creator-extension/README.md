# Chrome Extension

This folder contains a Manifest V3 Chrome extension for using TikTok Creator Lead Browser inside the Chrome session where you are already logged in.

The extension does not automate engagement. It only reads public information visible on the TikTok page you opened manually.

## Install Locally

1. Open Chrome.
2. Go to `chrome://extensions`.
3. Enable `Developer mode`.
4. Click `Load unpacked`.
5. Select this folder:

```text
F:\AI Agent\Auto boker grab\tiktok-creator-lead-browser\chrome-extension
```

6. Pin `TikTok Creator Lead Browser` from the extensions menu. Clicking the extension icon opens the side panel.

If the extension was already installed, click the reload button on the extension card after file changes.

## How To Use

1. Open your already logged-in TikTok page.
2. Click the extension icon to open the side panel.
3. Enter a search keyword.
4. Set `Lead Filters`. The default is visible email required and minimum 1000 followers.
5. Open your already logged-in TikTok page first, then click `Search In Page`. The extension types the keyword into TikTok's visible search box in the current tab, clicks the `Videos` tab, scans visible results, and clicks the first visible video.
6. Scroll TikTok manually if you want more visible results.
7. Click `Scan Page` to collect visible video links into the local queue.
8. Click `Open Next Profile` to open one queued creator profile in a new tab.
9. Wait for the profile page to load.
10. Click `Scan Page` again.
11. If the creator has a visible valid email and meets the follower threshold, the lead is saved.
12. If the creator does not match the filters, the profile is recorded as skipped.
13. Export email leads with `Export CSV` or `Export JSON`.
14. Export the full local state with `Export Backup`.

## Auto Run

Auto run is still supervised visible browsing. It does not interact with TikTok users.

1. Open the side panel when possible.
2. Enter a search keyword.
3. Set `Lead Filters`. The default is visible email required and minimum 1000 followers.
4. Set `Scrolls`, `Profiles`, `Delay min`, `Delay max`, and rest-break settings. The default is a fast human pace: 2-4 second random delays, a short page-settle wait, and a rest break every 15 checked profiles.
5. Click `Start Auto Run`.
6. The extension uses the current logged-in TikTok browser session. It does not launch a separate Chrome profile and does not navigate to a search URL fallback if the search box is missing.
7. If the current tab is a TikTok video search results page, it works through the visible result cards one by one.
8. On search results pages, it clicks a result card, checks the opened video, opens the creator profile in a temporary tab when needed, closes the profile tab, then clicks TikTok's video close button to return to the search results page.
9. When the currently visible search results are exhausted, it scrolls the search results page to load more and continues.
10. If the current tab is already a TikTok video page, it starts from that video directly.
11. Otherwise, it types into the visible search box, submits the search, clicks the `Videos` tab, and then uses the search-results workflow.
12. Before opening a creator profile, it checks whether the username or source video was already handled and skips duplicates.
13. If the current video is visibly unavailable or cannot be played, it closes the video view and continues with the next search result.
14. It keeps looping until the configured task target is reached or `Stop Auto` is clicked.
10. It saves only profiles with visible valid email addresses and followers greater than or equal to the configured minimum.
11. Every configured number of processed videos, it takes a random rest break between `Rest min` and `Rest max`.
12. Click `Stop Auto` to stop after the current step.

If login, CAPTCHA, verification, age, region, or unusual access text is detected, auto run pauses. Handle it manually in the visible browser, then start auto run again.

Keep the side panel open while auto run is active. Chrome stops popup scripts when a popup loses focus, so long runs are intentionally handled from the side panel.

The side panel shows:

- `Leads`: saved creators with visible valid email addresses.
- `Queue`: visible creator profiles found from search results but not handled yet.
- `Skipped`: profiles checked but rejected by filters.
- `Next Queue`: the next few queued profiles.
- `Recent Leads`: the latest saved email leads.

## Compliance

- No auto-like.
- No auto-comment.
- No auto-follow.
- No auto-message.
- No posting.
- No CAPTCHA bypass.
- No login bypass.
- No proxy.
- No fingerprint evasion.
- No hidden scraping.
- Only currently visible TikTok page text and visible links are read.

## Data Storage

Data is stored locally in Chrome extension storage. CSV, JSON, and backup exports are downloaded with Chrome's normal download flow.
