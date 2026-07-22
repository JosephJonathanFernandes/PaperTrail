chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "verify-citation",
    title: "Verify with PaperTrail",
    contexts: ["selection"]
  });
});

// Chrome's native PDF viewer URL prefix — content scripts cannot inject into it.
const PDF_VIEWER_ORIGIN = "chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai";

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "verify-citation") {

    // Guard: Chrome's native PDF viewer doesn't support content script injection.
    // The PDF viewer runs in a sandboxed extension context that blocks message passing.
    if (tab.url && tab.url.startsWith(PDF_VIEWER_ORIGIN)) {
      // Can't inject a toast — open a notification instead via badge or alert
      chrome.action && chrome.action.setBadgeText && chrome.action.setBadgeText({ text: "PDF", tabId: tab.id });
      console.warn(
        "PaperTrail: Chrome's native PDF viewer doesn't support text injection. " +
        "Please copy the citation text and verify it from any regular webpage."
      );
      return;
    }

    // 1. Text Normalization: Clean up ragged highlighted text
    let rawText = info.selectionText;
    
    // Remove weird line breaks (common in PDFs), multiple spaces, and brackets like [1] or (1998)
    let cleanedText = rawText
      .replace(/[\r\n]+/g, " ")       // Remove linebreaks
      .replace(/\[\d+\]/g, "")        // Remove [1], [23]
      .replace(/\s{2,}/g, " ")        // Remove multiple spaces
      .trim();
      
    // Truncate to 500 characters to prevent overly long requests
    if (cleanedText.length > 500) {
      cleanedText = cleanedText.substring(0, 500);
    }

    // 2. Tell the content script to show a Loading Toast immediately
    chrome.tabs.sendMessage(tab.id, { action: "showLoading" });

    // 3. Hit the local API with a 15-second timeout so a hung server
    //    doesn't leave the user with a stuck loading spinner forever.
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    fetch("http://127.0.0.1:5000/find_paper", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: cleanedText }),
      signal: controller.signal
    })
    .then(response => {
      clearTimeout(timeoutId);
      return response.json();
    })
    .then(data => {
      // 4. Send the result back to the content script to update the toast
      chrome.tabs.sendMessage(tab.id, { action: "showResult", payload: data });
    })
    .catch(error => {
      clearTimeout(timeoutId);
      // Distinguish between "server not running" and other network failures.
      const errStr = error.toString();
      let userMessage;
      if (error.name === "AbortError") {
        userMessage = "timeout";
      } else if (
        errStr.includes("Failed to fetch") ||
        errStr.includes("ERR_CONNECTION_REFUSED") ||
        errStr.includes("NetworkError")
      ) {
        userMessage = "connection_refused";
      } else {
        userMessage = errStr;
      }
      chrome.tabs.sendMessage(tab.id, { action: "showError", errorType: userMessage });
    });
  }
});
