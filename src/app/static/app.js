const modeTabs = document.querySelectorAll(".mode-tab");
const workspaces = document.querySelectorAll('[role="tabpanel"]');

function selectWorkspace(tab) {
  for (const candidate of modeTabs) {
    const isSelected = candidate === tab;
    candidate.classList.toggle("is-active", isSelected);
    candidate.setAttribute("aria-selected", String(isSelected));
  }

  for (const workspace of workspaces) {
    workspace.hidden = workspace.id !== tab.dataset.panel;
  }
}

for (const tab of modeTabs) {
  tab.addEventListener("click", () => selectWorkspace(tab));
}

function syncModelOptions(providerSelect, modelSelect) {
  const selectedProvider = providerSelect.value;
  let firstMatchingOption = null;

  for (const option of modelSelect.options) {
    const matchesProvider = option.dataset.provider === selectedProvider;
    option.hidden = !matchesProvider;
    option.disabled = !matchesProvider;

    if (matchesProvider && firstMatchingOption === null) {
      firstMatchingOption = option;
    }
  }

  if (firstMatchingOption !== null) {
    modelSelect.value = firstMatchingOption.value;
  }
}

function createRequestId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }

  return `browser-${Date.now()}`;
}

async function responseErrorMessage(response) {
  try {
    const data = await response.json();
    return data.error?.message || "The request failed safely.";
  } catch {
    return "The request failed safely.";
  }
}

function showFormError(status, message) {
  status.textContent = message;
  status.classList.add("error-message");
}

// Week 2: structured ticket triage.
const triageForm = document.querySelector("#triage-form");
const triageProvider = document.querySelector("#triage-provider");
const triageModel = document.querySelector("#triage-model");
const ticketId = document.querySelector("#ticket-id");
const ticketChannel = document.querySelector("#ticket-channel");
const ticketSubject = document.querySelector("#ticket-subject");
const ticketBody = document.querySelector("#ticket-body");
const ticketBodyCount = document.querySelector("#ticket-body-count");
const triageButton = document.querySelector("#triage-button");
const triageCancelButton = document.querySelector("#triage-cancel-button");
const triageButtonLabel = triageButton.querySelector(".button-label");
const triageButtonProgress = triageButton.querySelector(".button-progress");
const triageStatus = document.querySelector("#triage-status");
const triageResultPanel = document.querySelector("#triage-result");

let activeTriageRequest = null;

const triageFields = {
  provider: document.querySelector("#triage-result-provider"),
  category: document.querySelector("#triage-category"),
  priority: document.querySelector("#triage-priority"),
  sentiment: document.querySelector("#triage-sentiment"),
  humanReview: document.querySelector("#triage-human-review"),
  confidence: document.querySelector("#triage-confidence"),
  summary: document.querySelector("#triage-summary"),
  requestedAction: document.querySelector("#triage-requested-action"),
  rationale: document.querySelector("#triage-rationale"),
  model: document.querySelector("#triage-metric-model"),
  latency: document.querySelector("#triage-metric-latency"),
  inputTokens: document.querySelector("#triage-metric-input-tokens"),
  outputTokens: document.querySelector("#triage-metric-output-tokens"),
  attemptCount: document.querySelector("#triage-metric-attempt-count"),
  requestId: document.querySelector("#triage-metric-request-id"),
  providerRequestId: document.querySelector(
    "#triage-metric-provider-request-id",
  ),
};

function formatLabel(value) {
  return value.replaceAll("_", " ");
}

function setTriageBusy(isBusy) {
  for (const control of [
    triageProvider,
    triageModel,
    ticketId,
    ticketChannel,
    ticketSubject,
    ticketBody,
  ]) {
    control.disabled = isBusy;
  }

  triageButton.disabled = isBusy;
  triageCancelButton.hidden = !isBusy;
  triageButtonLabel.hidden = isBusy;
  triageButtonProgress.hidden = !isBusy;
}

function renderTriageResult(data) {
  const triage = data.triage;
  triageFields.provider.textContent = data.provider;
  triageFields.category.textContent = formatLabel(triage.category);
  triageFields.priority.textContent = triage.priority;
  triageFields.priority.dataset.priority = triage.priority;
  triageFields.sentiment.textContent = triage.sentiment;
  triageFields.humanReview.textContent = triage.requires_human_review
    ? "Required"
    : "Not required";
  triageFields.confidence.textContent = `${(triage.confidence * 100).toFixed(0)}%`;
  triageFields.summary.textContent = triage.summary;
  triageFields.requestedAction.textContent = triage.requested_action;
  triageFields.rationale.textContent = triage.rationale;
  triageFields.model.textContent = data.model;
  triageFields.latency.textContent = `${data.latency_ms.toFixed(2)} ms`;
  triageFields.inputTokens.textContent = data.input_tokens;
  triageFields.outputTokens.textContent = data.output_tokens;
  triageFields.attemptCount.textContent = data.attempt_count;
  triageFields.requestId.textContent = data.request_id;
  triageFields.providerRequestId.textContent =
    data.provider_request_id || "Not supplied";
  triageResultPanel.hidden = false;
}

triageProvider.addEventListener("change", () => {
  syncModelOptions(triageProvider, triageModel);
});

ticketBody.addEventListener("input", () => {
  ticketBodyCount.textContent =
    `${ticketBody.value.length} / ${ticketBody.maxLength}`;
});

triageCancelButton.addEventListener("click", () => {
  activeTriageRequest?.abort();
});

triageForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (
    !ticketId.value.trim() ||
    !ticketSubject.value.trim() ||
    !ticketBody.value.trim()
  ) {
    showFormError(triageStatus, "Enter a ticket ID, subject, and description.");
    return;
  }

  triageStatus.classList.remove("error-message");
  triageStatus.textContent = "Requesting a validated classification…";
  triageResultPanel.hidden = true;
  setTriageBusy(true);
  activeTriageRequest = new AbortController();

  try {
    const response = await fetch("/api/triage", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": createRequestId(),
      },
      body: JSON.stringify({
        provider: triageProvider.value,
        model: triageModel.value,
        ticket: {
          ticket_id: ticketId.value.trim(),
          subject: ticketSubject.value.trim(),
          body: ticketBody.value.trim(),
          channel: ticketChannel.value,
        },
      }),
      signal: activeTriageRequest.signal,
    });

    if (!response.ok) {
      throw new Error(await responseErrorMessage(response));
    }

    const data = await response.json();
    renderTriageResult(data);
    triageStatus.textContent = "Ticket classified and schema validated.";
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      triageStatus.classList.remove("error-message");
      triageStatus.textContent = "Classification cancelled.";
    } else {
      const message =
        error instanceof Error ? error.message : "The request failed.";
      showFormError(triageStatus, message);
    }
  } finally {
    activeTriageRequest = null;
    setTriageBusy(false);
  }
});

syncModelOptions(triageProvider, triageModel);

// Week 1: streaming prompt playground.
const form = document.querySelector("#generation-form");
const providerSelect = document.querySelector("#provider");
const modelSelect = document.querySelector("#model");
const promptInput = document.querySelector("#prompt");
const promptCount = document.querySelector("#prompt-count");
const submitButton = document.querySelector("#generate-button");
const cancelButton = document.querySelector("#cancel-button");
const buttonLabel = submitButton.querySelector(".button-label");
const buttonProgress = submitButton.querySelector(".button-progress");
const formStatus = document.querySelector("#form-status");
const resultPanel = document.querySelector("#result");

let activeRequest = null;

const resultFields = {
  provider: document.querySelector("#result-provider"),
  text: document.querySelector("#result-text"),
  model: document.querySelector("#metric-model"),
  latency: document.querySelector("#metric-latency"),
  inputTokens: document.querySelector("#metric-input-tokens"),
  outputTokens: document.querySelector("#metric-output-tokens"),
  finishReason: document.querySelector("#metric-finish-reason"),
  requestId: document.querySelector("#metric-request-id"),
  providerRequestId: document.querySelector("#metric-provider-request-id"),
};

function setBusy(isBusy) {
  submitButton.disabled = isBusy;
  providerSelect.disabled = isBusy;
  modelSelect.disabled = isBusy;
  promptInput.disabled = isBusy;
  cancelButton.hidden = !isBusy;
  buttonLabel.hidden = isBusy;
  buttonProgress.hidden = !isBusy;
}

function showStreamError(message) {
  showFormError(formStatus, message);
  resultPanel.classList.remove("is-streaming");
}

function resetMetrics() {
  resultFields.latency.textContent = "—";
  resultFields.inputTokens.textContent = "—";
  resultFields.outputTokens.textContent = "—";
  resultFields.finishReason.textContent = "—";
  resultFields.providerRequestId.textContent = "—";
}

function handleStreamEvent(eventName, data) {
  if (eventName === "start") {
    resultFields.provider.textContent = data.provider;
    resultFields.model.textContent = data.model;
    resultFields.requestId.textContent = data.request_id;
    resultFields.text.textContent = "";
    resetMetrics();
    resultPanel.hidden = false;
    resultPanel.classList.add("is-streaming");
    formStatus.textContent = "Streaming response…";
    return;
  }

  if (eventName === "delta") {
    resultFields.text.textContent += data.text;
    resultFields.text.scrollTop = resultFields.text.scrollHeight;
    return;
  }

  if (eventName === "complete") {
    resultFields.provider.textContent = data.provider;
    resultFields.model.textContent = data.model;
    resultFields.latency.textContent = `${data.latency_ms.toFixed(2)} ms`;
    resultFields.inputTokens.textContent = data.input_tokens;
    resultFields.outputTokens.textContent = data.output_tokens;
    resultFields.finishReason.textContent = data.finish_reason;
    resultFields.requestId.textContent = data.request_id;
    resultFields.providerRequestId.textContent =
      data.provider_request_id || "Not supplied";
    resultPanel.classList.remove("is-streaming");
    formStatus.textContent = "Response completed.";
    return;
  }

  if (eventName === "error") {
    throw new Error(data.message || "The stream failed safely.");
  }
}

function parseSseBlock(block) {
  let eventName = "message";
  const dataLines = [];

  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trimStart();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return {
    eventName,
    data: JSON.parse(dataLines.join("\n")),
  };
}

async function readSseResponse(response) {
  if (response.body === null) {
    throw new Error("This browser did not expose a streaming response body.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = parseSseBlock(block);
        if (event !== null) {
          handleStreamEvent(event.eventName, event.data);
          if (event.eventName === "complete") {
            completed = true;
          }
        }
        boundary = buffer.indexOf("\n\n");
      }

      if (done) {
        break;
      }
    }

    if (buffer.trim()) {
      const event = parseSseBlock(buffer);
      if (event !== null) {
        handleStreamEvent(event.eventName, event.data);
        if (event.eventName === "complete") {
          completed = true;
        }
      }
    }

    if (!completed) {
      throw new Error("The stream ended before a completion event arrived.");
    }
  } finally {
    reader.releaseLock();
  }
}

providerSelect.addEventListener("change", () => {
  syncModelOptions(providerSelect, modelSelect);
});

promptInput.addEventListener("input", () => {
  promptCount.textContent = `${promptInput.value.length} / ${promptInput.maxLength}`;
});

cancelButton.addEventListener("click", () => {
  activeRequest?.abort();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const prompt = promptInput.value.trim();
  if (!prompt) {
    showStreamError("Enter a prompt before generating a response.");
    promptInput.focus();
    return;
  }

  formStatus.classList.remove("error-message");
  formStatus.textContent = "Connecting to the selected provider…";
  resultPanel.hidden = true;
  setBusy(true);
  activeRequest = new AbortController();

  try {
    const response = await fetch("/api/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": createRequestId(),
      },
      body: JSON.stringify({
        provider: providerSelect.value,
        model: modelSelect.value,
        prompt,
      }),
      signal: activeRequest.signal,
    });

    if (!response.ok) {
      throw new Error(await responseErrorMessage(response));
    }

    await readSseResponse(response);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      formStatus.classList.remove("error-message");
      formStatus.textContent = "Streaming cancelled.";
      resultPanel.classList.remove("is-streaming");
    } else {
      const message =
        error instanceof Error ? error.message : "The request failed.";
      showStreamError(message);
    }
  } finally {
    activeRequest = null;
    setBusy(false);
  }
});

syncModelOptions(providerSelect, modelSelect);
