document.addEventListener("DOMContentLoaded", () => {
    const urlParams = new URLSearchParams(window.location.search);
    const query = urlParams.get('query');

    const container = document.getElementById('container');
    const spinner = document.getElementById('spinner');
    const statusEl = document.getElementById('status');
    const messageEl = document.getElementById('message');
    const linkEl = document.getElementById('action-link');

    if (!query) {
        showError("No query provided.");
        return;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);

    fetch("http://127.0.0.1:5000/find_paper", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query }),
        signal: controller.signal
    })
    .then(response => {
        clearTimeout(timeoutId);
        return response.json();
    })
    .then(data => {
        spinner.style.display = 'none';
        
        // Ensure data exists, might be a 404 from our API
        if (data.status === "success" && data.pdf_url) {
            if (data.metadata && data.metadata.is_retracted) {
                container.className = "container retracted";
                statusEl.textContent = "⚠️ Retracted Paper";
                messageEl.textContent = "This paper has been retracted. View with caution.";
            } else {
                container.className = "container success";
                statusEl.textContent = "✅ Verified Open Access";
                messageEl.textContent = data.metadata ? data.metadata.title : "Paper found";
            }
            linkEl.href = data.pdf_url;
            linkEl.style.display = "inline-block";
            linkEl.textContent = "View PDF";
        } else if (data.status === "not_found" && data.fallback_options && data.fallback_options.length > 0) {
            container.className = "container fallback";
            statusEl.textContent = "⚠️ No Free PDF Found";
            messageEl.textContent = "We couldn't find an open access PDF, but we found a fallback link.";
            linkEl.href = data.fallback_options[0].url;
            linkEl.style.display = "inline-block";
            linkEl.textContent = "View Fallback";
        } else {
            container.className = "container error";
            statusEl.textContent = "❌ Unverified";
            messageEl.textContent = data.message || "Could not verify this citation.";
        }
    })
    .catch(error => {
        clearTimeout(timeoutId);
        showError(error.name === "AbortError" ? "Request timed out." : "Server unreachable.");
    });

    function showError(msg) {
        spinner.style.display = 'none';
        container.className = "container error";
        statusEl.textContent = "❌ Error";
        messageEl.textContent = msg;
    }
});
