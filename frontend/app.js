/**
 * Case Intel Frontend - Minimal Single Page App
 * Vanilla JavaScript, no dependencies
 */

const API_BASE = "http://localhost:8000/api";

// State
let currentCaseId = null;
let currentConversationId = null;
let isLoading = false;

// ===== INITIALIZATION =====

document.addEventListener("DOMContentLoaded", () => {
  loadCases();
  setupEventListeners();
});

function setupEventListeners() {
  // File drop zone
  const dropZone = document.getElementById("file-drop-zone");
  dropZone.addEventListener("click", () => {
    document.getElementById("doc-file").click();
  });

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("drag-over");
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      document.getElementById("doc-file").files = files;
      document.getElementById("file-name").textContent = `✓ ${files[0].name}`;
      document.getElementById("file-name").style.display = "block";
    }
  });

  document.getElementById("doc-file").addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      document.getElementById("file-name").textContent =
        `✓ ${e.target.files[0].name}`;
      document.getElementById("file-name").style.display = "block";
    }
  });

  // Enter to send in chat
  document.getElementById("query-input").addEventListener("keypress", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  });
}

// ===== CASE MANAGEMENT =====

async function loadCases() {
  try {
    const res = await fetch(`${API_BASE}/cases/`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const cases = await res.json();
    const list = document.getElementById("cases-list");

    if (cases.length === 0) {
      list.innerHTML =
        '<div class="empty-state" style="padding: 20px 10px;"><p>No cases yet</p></div>';
      return;
    }

    list.innerHTML = cases
      .map(
        (c) => `
      <div class="case-item ${c.id === currentCaseId ? "active" : ""}" onclick="selectCase(${c.id})">
        <div class="case-item-number">${c.case_number}</div>
        <div class="case-item-title">${c.title}</div>
        <div class="case-item-meta">${c.document_count} document${c.document_count !== 1 ? "s" : ""}</div>
      </div>
    `,
      )
      .join("");
  } catch (err) {
    console.error("Failed to load cases:", err);
    document.getElementById("cases-list").innerHTML =
      '<div class="empty-state"><p>Failed to load cases</p></div>';
  }
}

async function selectCase(caseId) {
  currentCaseId = caseId;
  currentConversationId = null;
  clearMessages();

  try {
    const caseRes = await fetch(`${API_BASE}/cases/${caseId}/`);
    if (!caseRes.ok) throw new Error(`Case not found`);
    const caseData = await caseRes.json();

    const docRes = await fetch(`${API_BASE}/documents/?case_id=${caseId}`);
    const docs = docRes.ok ? await docRes.json() : [];

    // Update sidebar
    document.querySelectorAll(".case-item").forEach((el) => {
      el.classList.remove("active");
    });
    // Find the case item by ID and mark it active
    const caseItems = document.querySelectorAll(".case-item");
    caseItems.forEach((el) => {
      if (el.textContent.includes(caseData.case_number)) {
        el.classList.add("active");
      }
    });

    // Render case details
    let html = `
      <h2>${caseData.case_number}: ${caseData.title}</h2>
      <div class="case-meta">
        <div class="case-meta-field">
          <div class="case-meta-label">Client</div>
          <div class="case-meta-value">${caseData.client_name}</div>
        </div>
        <div class="case-meta-field">
          <div class="case-meta-label">Status</div>
          <div class="case-meta-value">${caseData.status}</div>
        </div>
        ${
          caseData.opposing_party
            ? `
          <div class="case-meta-field">
            <div class="case-meta-label">Opposing Party</div>
            <div class="case-meta-value">${caseData.opposing_party}</div>
          </div>
        `
            : ""
        }
        <div class="case-meta-field">
          <div class="case-meta-label">Case Type</div>
          <div class="case-meta-value">${caseData.case_type || "N/A"}</div>
        </div>
      </div>

      <div class="documents-section">
        <h3>📄 Documents</h3>
    `;

    if (docs.length === 0) {
      html +=
        '<p style="color: #95a5a6; font-style: italic;">No documents uploaded yet</p>';
    } else {
      html += docs
        .map(
          (d) => `
        <div class="document-item">
          <div class="document-info">
            <div class="document-name">${d.filename}</div>
            <div class="document-status ${d.processing_status}">
              ${d.processing_status} ${d.chunk_count ? `• ${d.chunk_count} chunks` : ""}
            </div>
          </div>
          <div></div>
          <div class="document-actions">
            ${
              d.processing_status === "pending"
                ? `
              <button class="btn-small" onclick="processDocument(${d.id}, event)">Process</button>
            `
                : ""
            }
            <button class="btn-small danger" onclick="deleteDocument(${d.id}, event)">Delete</button>
          </div>
        </div>
      `,
        )
        .join("");
    }

    html += `
      </div>
      <div class="main-buttons">
        <button class="btn-primary" onclick="showUploadModal()">📤 Upload Document</button>
        <button class="btn-primary" style="background: #27ae60;" onclick="startNewChat()">💬 Chat with AI</button>
      </div>
    `;

    document.getElementById("case-details").innerHTML = html;
    document.getElementById("chat-title").textContent =
      `💬 ${caseData.case_number}: ${caseData.title}`;
  } catch (err) {
    console.error("Failed to load case:", err);
    document.getElementById("case-details").innerHTML = `
      <div class="empty-state">
        <h3>⚠️ Failed to Load Case</h3>
        <p>${err.message}</p>
      </div>
    `;
  }
}

async function submitNewCase(event) {
  event.preventDefault();

  const caseData = {
    case_number: document.getElementById("case-number").value,
    title: document.getElementById("case-title").value,
    client_name: document.getElementById("case-client").value,
    opposing_party: document.getElementById("case-opposing").value || null,
    case_type: document.getElementById("case-type").value,
    priority: document.getElementById("case-priority").value,
    status: "open",
  };

  try {
    const res = await fetch(`${API_BASE}/cases/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(caseData),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const newCase = await res.json();
    closeModal("new-case-modal");
    event.target.reset();

    await loadCases();
    selectCase(newCase.id);
  } catch (err) {
    alert(`Failed to create case: ${err.message}`);
  }
}

// ===== DOCUMENT MANAGEMENT =====

function showUploadModal() {
  if (!currentCaseId) {
    alert("Please select a case first");
    return;
  }
  document.getElementById("file-drop-zone").classList.remove("drag-over");
  document.getElementById("doc-file").value = "";
  document.getElementById("file-name").style.display = "none";
  openModal("upload-modal");
}

async function submitUpload(event) {
  event.preventDefault();

  const file = document.getElementById("doc-file").files[0];
  if (!file) {
    alert("Please select a file");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("case_id", currentCaseId);
  formData.append("document_type", document.getElementById("doc-type").value);

  try {
    const res = await fetch(`${API_BASE}/documents/upload/`, {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || err.file?.[0] || `HTTP ${res.status}`);
    }

    closeModal("upload-modal");
    alertSuccess("Document uploaded successfully!");
    selectCase(currentCaseId); // Refresh
  } catch (err) {
    alertError(`Upload failed: ${err.message}`);
  }
}

async function processDocument(docId, event) {
  event.stopPropagation();

  try {
    const res = await fetch(`${API_BASE}/documents/${docId}/process/`, {
      method: "POST",
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    alertSuccess("Document processing started!");
    selectCase(currentCaseId); // Refresh
  } catch (err) {
    alertError(`Processing failed: ${err.message}`);
  }
}

async function deleteDocument(docId, event) {
  event.stopPropagation();

  if (!confirm("Delete this document? This cannot be undone.")) {
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/documents/${docId}/`, {
      method: "DELETE",
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    alertSuccess("Document deleted");
    selectCase(currentCaseId); // Refresh
  } catch (err) {
    alertError(`Delete failed: ${err.message}`);
  }
}

// ===== CHAT =====

function startNewChat() {
  if (!currentCaseId) {
    alert("Please select a case first");
    return;
  }
  currentConversationId = null;
  clearMessages();
  document.getElementById("query-input").focus();
  addMessage(
    "info",
    `Chat session started for case ${currentCaseId}. Ask any questions about the documents in this case!`,
  );
}

async function sendChat() {
  if (isLoading) return;

  const query = document.getElementById("query-input").value.trim();
  if (!query) return;

  if (!currentCaseId) {
    addMessage("error", "Please select a case first");
    return;
  }

  // User message
  addMessage("user", query);
  document.getElementById("query-input").value = "";

  isLoading = true;

  try {
    const res = await fetch(`${API_BASE}/chat/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        case_id: currentCaseId,
        conversation_id: currentConversationId,
      }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();

    // Update conversation ID
    if (data.conversation_id) {
      currentConversationId = data.conversation_id;
    }

    // Build response with citations
    let responseHtml = data.answer;

    if (data.citations && data.citations.length > 0) {
      responseHtml += '<div class="citation-block">';
      responseHtml += "<strong>📎 Sources:</strong><br>";
      data.citations.forEach((c, i) => {
        const text = c.citation_text || c.text || "Unknown source";
        responseHtml += `<div class="citation">Citation ${i + 1}: "${text.substring(0, 80)}..."</div>`;
      });
      responseHtml += "</div>";
    }

    addMessage("assistant", responseHtml);

    // Show confidence and query type
    const confidence = (data.confidence * 100).toFixed(0);
    addMessage(
      "info",
      `🎯 Confidence: ${confidence}% | Query Type: ${data.query_type}`,
    );

    if (data.requires_clarification && data.clarification_question) {
      addMessage("info", `❓ ${data.clarification_question}`);
    }
  } catch (err) {
    addMessage("error", `Error: ${err.message}`);
  } finally {
    isLoading = false;
  }
}

function clearChat() {
  clearMessages();
  currentConversationId = null;
  addMessage("info", "Chat cleared. Starting a new conversation.");
}

// ===== UI HELPERS =====

function addMessage(role, content) {
  const container = document.getElementById("messages-container");
  const msg = document.createElement("div");
  msg.className = `message ${role}`;
  msg.innerHTML = content;
  container.appendChild(msg);
  container.scrollTop = container.scrollHeight;
}

function clearMessages() {
  document.getElementById("messages-container").innerHTML = "";
}

function alertSuccess(message) {
  addMessage("info", `✓ ${message}`);
}

function alertError(message) {
  addMessage("error", `✗ ${message}`);
}

function openModal(modalId) {
  document.getElementById(modalId).classList.add("active");
}

function closeModal(modalId) {
  document.getElementById(modalId).classList.remove("active");
}

function showNewCaseModal() {
  openModal("new-case-modal");
}

// Close modals when clicking outside
document.addEventListener("click", (e) => {
  if (e.target.classList.contains("modal")) {
    e.target.classList.remove("active");
  }
});

// Handle modal form reset on close
document.getElementById("new-case-modal").addEventListener("click", (e) => {
  if (e.target.classList.contains("modal")) {
    document.querySelector("#new-case-modal form").reset();
  }
});

document.getElementById("upload-modal").addEventListener("click", (e) => {
  if (e.target.classList.contains("modal")) {
    document.querySelector("#upload-modal form").reset();
    document.getElementById("file-name").style.display = "none";
  }
});
