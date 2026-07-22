chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "verify-citation",
    title: "Verify with PaperTrail",
    contexts: ["selection"]
  });
});

// Chrome's built-in PDF viewer extension ID.
// IMPORTANT — Browser-specificity constraint:
//   - Chrome stable: chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai (verified as of Chrome 120+)
//   - Microsoft Edge: uses a DIFFERENT built-in PDF viewer ID (edge://pdf-viewer/)
//   - Brave: inherits Chromium's viewer; may use the same ID but is not guaranteed
//   - Firefox: does not apply (different extension architecture)
//
// This approach is Chrome-specific by design. Cross-browser support (Edge, Brave)
// is a known gap — see test matrix B5 #103. If this ID changes in a future Chrome
// release, the guard below will silently stop working for PDF tabs (it will fall
// through to content-script injection, which will then fail with no visible error).
// A more robust long-term solution: use chrome.tabs.detectLanguage or check
// tab.url for "file://*.pdf" patterns in addition to the extension URL prefix.
const PDF_VIEWER_ORIGIN = "chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai";

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "verify-citation") {

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

    // Guard: Chrome/Edge/Brave native PDF viewers don't support content script injection.
    const isPDFViewer = tab.url && (
      tab.url.startsWith("chrome-extension://") || 
      tab.url.startsWith("edge://") ||
      tab.url.toLowerCase().endsWith(".pdf")
    );

    if (isPDFViewer) {
      // Open a popup window instead of injecting a toast
      chrome.windows.create({
        url: `pdf_result.html?query=${encodeURIComponent(cleanedText)}`,
        type: "popup",
        width: 450,
        height: 250,
        focused: true
      });
      return;
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
