chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(['tclabState'], (result) => {
    if (result.tclabState) {
      return;
    }

    chrome.storage.local.set({
      tclabState: {
        leads: [],
        sourceVideos: [],
        skippedProfiles: [],
        taskLogs: [],
        pendingProfiles: [],
        settings: {
          currentKeyword: ''
        }
      }
    });
  });
});

chrome.action.onClicked.addListener(async (tab) => {
  if (!chrome.sidePanel?.open || !tab.windowId) {
    return;
  }

  await chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => undefined);
});
