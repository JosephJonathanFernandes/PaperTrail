// Listen for messages from background.js
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "showLoading") {
    injectToast("Verifying citation...", "loading");
  } else if (request.action === "showResult") {
    updateToastWithResult(request.payload);
  } else if (request.action === "showError") {
    updateToastWithError(request.error);
  }
});

let currentToast = null;

function injectToast(message, type) {
  // Remove existing toast if there is one
  if (currentToast) {
    currentToast.remove();
  }

  currentToast = document.createElement("div");
  currentToast.className = `papertrail-toast papertrail-${type}`;
  
  const content = document.createElement("div");
  content.className = "papertrail-content";
  
  if (type === "loading") {
    content.innerHTML = `<div class="papertrail-spinner"></div><span>${message}</span>`;
  } else {
    content.innerHTML = `<span>${message}</span>`;
  }
  
  const closeBtn = document.createElement("button");
  closeBtn.innerText = "×";
  closeBtn.className = "papertrail-close";
  closeBtn.onclick = () => currentToast.remove();

  currentToast.appendChild(content);
  currentToast.appendChild(closeBtn);
  document.body.appendChild(currentToast);
}

function updateToastWithResult(data) {
  if (!currentToast) injectToast("", "info");

  let html = "";
  if (data.status === "success") {
    currentToast.className = "papertrail-toast papertrail-success";
    html = `
      <strong>✅ ${data.metadata.title || "Paper Found"}</strong><br>
      <a href="${data.pdf_url}" target="_blank" style="color: white; text-decoration: underline;">View PDF</a>
    `;
    // Add warnings if tier is low
    if (data.confidence_tier === "LOW" && data.flags && data.flags.length > 0) {
      currentToast.className = "papertrail-toast papertrail-warning";
      html += `<div style="font-size: 12px; margin-top: 5px;">⚠️ <strong>Warning:</strong> ${data.flags[0]}</div>`;
    }
  } else if (data.status === "unverified") {
    currentToast.className = "papertrail-toast papertrail-error";
    html = `<strong>❌ Unverified Citation</strong><br>Could not find this paper in any canonical database.`;
  } else {
    currentToast.className = "papertrail-toast papertrail-warning";
    html = `<strong>⚠️ No PDF Found</strong><br>Paper exists but no free legal access was found.`;
  }

  currentToast.querySelector(".papertrail-content").innerHTML = html;
  
  // Auto dismiss after 10 seconds unless it's a success with a link
  if (data.status !== "success") {
      setTimeout(() => {
        if (currentToast) currentToast.remove();
      }, 10000);
  }
}

function updateToastWithError(error) {
  if (!currentToast) injectToast("", "error");
  currentToast.className = "papertrail-toast papertrail-error";
  currentToast.querySelector(".papertrail-content").innerHTML = `<strong>Backend Error</strong><br>Is your local Flask server running?<br><small>${error}</small>`;
}
