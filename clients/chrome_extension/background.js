chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "verify-citation",
    title: "Verify with PaperTrail",
    contexts: ["selection"]
  });
});

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

    // 2. Tell the content script to show a Loading Toast immediately
    chrome.tabs.sendMessage(tab.id, { action: "showLoading" });

    // 3. Hit the local API
    fetch("http://127.0.0.1:5000/find_paper", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ query: cleanedText })
    })
    .then(response => response.json())
    .then(data => {
      // 4. Send the result back to the content script to update the toast
      chrome.tabs.sendMessage(tab.id, { action: "showResult", payload: data });
    })
    .catch(error => {
      chrome.tabs.sendMessage(tab.id, { action: "showError", error: error.toString() });
    });
  }
});
