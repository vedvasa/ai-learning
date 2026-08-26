const modeTabs = document.querySelectorAll(".mode-tab");
const workspaces = document.querySelectorAll('[role="tabpanel"]');

function selectWorkspace(tab) {
  for (const candidate of modeTabs) {
    const isSelected = candidate === tab;
    candidate.classList.toggle("is-active", isSelected);
    candidate.setAttribute("aria-selected", String(isSelected));
    candidate.tabIndex = isSelected ? 0 : -1;
  }

  for (const workspace of workspaces) {
    workspace.hidden = workspace.id !== tab.dataset.panel;
  }
}

for (const tab of modeTabs) {
  tab.addEventListener("click", () => selectWorkspace(tab));
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) {
      return;
    }

    event.preventDefault();
    const tabs = [...modeTabs];
    const direction = event.key === "ArrowRight" ? 1 : -1;
    const nextIndex = (tabs.indexOf(tab) + direction + tabs.length) % tabs.length;
    const nextTab = tabs[nextIndex];
    selectWorkspace(nextTab);
    nextTab.focus();
  });
}

const initialTab = document.querySelector(".mode-tab.is-active");
if (initialTab !== null) {
  selectWorkspace(initialTab);
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

// Week 3: citation-grounded question answering.
const answerForm = document.querySelector("#answer-form");
const answerProvider = document.querySelector("#answer-provider");
const answerModel = document.querySelector("#answer-model");
const answerTopK = document.querySelector("#answer-top-k");
const answerQuestion = document.querySelector("#answer-question");
const answerQuestionCount = document.querySelector("#answer-question-count");
const answerButton = document.querySelector("#answer-button");
const answerCancelButton = document.querySelector("#answer-cancel-button");
const answerButtonLabel = answerButton.querySelector(".button-label");
const answerButtonProgress = answerButton.querySelector(".button-progress");
const answerStatus = document.querySelector("#answer-status");
const answerResultPanel = document.querySelector("#answer-result");
const answerText = document.querySelector("#answer-text");
const answerSources = document.querySelector("#answer-sources");
const answerSourceCount = document.querySelector("#answer-source-count");

const answerFields = {
  provider: document.querySelector("#answer-result-provider"),
  outcome: document.querySelector("#answer-outcome"),
  model: document.querySelector("#answer-metric-model"),
  conversationId: document.querySelector("#answer-metric-conversation-id"),
  generationLatency: document.querySelector(
    "#answer-metric-generation-latency",
  ),
  embeddingLatency: document.querySelector(
    "#answer-metric-embedding-latency",
  ),
  generationTokens: document.querySelector(
    "#answer-metric-generation-tokens",
  ),
  attemptCount: document.querySelector("#answer-metric-attempt-count"),
  requestId: document.querySelector("#answer-metric-request-id"),
  providerRequestId: document.querySelector(
    "#answer-metric-provider-request-id",
  ),
};

let activeAnswerRequest = null;

function setAnswerBusy(isBusy) {
  for (const control of [
    answerProvider,
    answerModel,
    answerTopK,
    answerQuestion,
  ]) {
    control.disabled = isBusy;
  }

  answerButton.disabled = isBusy;
  answerCancelButton.hidden = !isBusy;
  answerButtonLabel.hidden = isBusy;
  answerButtonProgress.hidden = !isBusy;
}

function safeSourceUrl(value) {
  if (!value) {
    return null;
  }

  try {
    const url = new URL(value, globalThis.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function renderSourceTitle(source, number) {
  const safeUrl = safeSourceUrl(source.source_url);
  const title = source.title || source.document_key;
  if (safeUrl === null) {
    const label = document.createElement("span");
    label.className = "source-title";
    label.textContent = `${number}. ${title}`;
    return label;
  }

  const link = document.createElement("a");
  link.className = "source-title";
  link.href = safeUrl;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = `${number}. ${title}`;
  return link;
}

function renderSources(sources) {
  answerSources.replaceChildren();
  answerSourceCount.textContent = `${sources.length} ${
    sources.length === 1 ? "source" : "sources"
  }`;

  const sourceNumberById = new Map();
  for (const [index, source] of sources.entries()) {
    const number = index + 1;
    sourceNumberById.set(source.chunk_id, number);

    const item = document.createElement("li");
    item.id = `answer-source-${source.chunk_id}`;
    item.className = "source-card";

    const heading = document.createElement("div");
    heading.className = "source-card-heading";
    heading.append(renderSourceTitle(source, number));

    const similarity = document.createElement("span");
    similarity.className = "similarity-chip";
    similarity.textContent = `Similarity ${Number(source.similarity).toFixed(3)}`;
    heading.append(similarity);
    item.append(heading);

    if (source.heading_path.length > 0) {
      const section = document.createElement("p");
      section.className = "source-section-path";
      section.textContent = source.heading_path.join(" › ");
      item.append(section);
    }

    const path = document.createElement("code");
    path.className = "source-path";
    path.textContent = source.canonical_path;
    item.append(path);
    answerSources.append(item);
  }

  if (sources.length === 0) {
    const empty = document.createElement("li");
    empty.className = "source-empty";
    empty.textContent = "No source was cited because this answer abstained.";
    answerSources.append(empty);
  }

  return sourceNumberById;
}

function renderAnswerText(value, sourceNumberById) {
  answerText.replaceChildren();
  const sourceMarker = /\[source:([0-9a-fA-F-]{36})\]/g;
  let cursor = 0;

  for (const match of value.matchAll(sourceMarker)) {
    answerText.append(document.createTextNode(value.slice(cursor, match.index)));
    const sourceNumber = sourceNumberById.get(match[1]);
    if (sourceNumber === undefined) {
      answerText.append(document.createTextNode(match[0]));
    } else {
      const citation = document.createElement("a");
      citation.className = "citation-link";
      citation.href = `#answer-source-${match[1]}`;
      citation.textContent = `[${sourceNumber}]`;
      citation.setAttribute("aria-label", `View verified source ${sourceNumber}`);
      answerText.append(citation);
    }
    cursor = match.index + match[0].length;
  }

  answerText.append(document.createTextNode(value.slice(cursor)));
}

function renderAnswerResult(data) {
  const sourceNumberById = renderSources(data.sources);
  renderAnswerText(data.answer, sourceNumberById);

  answerFields.provider.textContent = data.provider;
  answerFields.outcome.textContent = data.abstained ? "Abstained" : "Grounded";
  answerFields.outcome.dataset.outcome = data.abstained
    ? "abstained"
    : "grounded";
  answerFields.model.textContent = data.model;
  answerFields.conversationId.textContent = data.conversation_id;
  answerFields.generationLatency.textContent = data.generation_performed
    ? `${data.generation_latency_ms.toFixed(2)} ms`
    : "Not called";
  answerFields.embeddingLatency.textContent =
    `${data.embedding_latency_ms.toFixed(2)} ms`;
  answerFields.generationTokens.textContent = data.generation_performed
    ? `${data.generation_input_tokens} in / ${data.generation_output_tokens} out`
    : "Not called";
  answerFields.attemptCount.textContent = data.attempt_count;
  answerFields.requestId.textContent = data.request_id;
  answerFields.providerRequestId.textContent =
    data.provider_request_id || "Not supplied";
  answerResultPanel.hidden = false;
}

answerProvider.addEventListener("change", () => {
  syncModelOptions(answerProvider, answerModel);
});

answerQuestion.addEventListener("input", () => {
  answerQuestionCount.textContent =
    `${answerQuestion.value.length} / ${answerQuestion.maxLength}`;
});

answerCancelButton.addEventListener("click", () => {
  activeAnswerRequest?.abort();
});

answerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = answerQuestion.value.trim();
  if (!question) {
    showFormError(answerStatus, "Enter a support question before searching.");
    answerQuestion.focus();
    return;
  }

  answerStatus.classList.remove("error-message");
  answerStatus.textContent = "Retrieving evidence and requesting an answer…";
  answerResultPanel.hidden = true;
  setAnswerBusy(true);
  activeAnswerRequest = new AbortController();

  try {
    const response = await fetch("/api/answer", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": createRequestId(),
      },
      body: JSON.stringify({
        provider: answerProvider.value,
        model: answerModel.value,
        question,
        top_k: Number(answerTopK.value),
      }),
      signal: activeAnswerRequest.signal,
    });

    if (!response.ok) {
      throw new Error(await responseErrorMessage(response));
    }

    const data = await response.json();
    renderAnswerResult(data);
    answerStatus.textContent = data.abstained
      ? "The answer abstained and the conversation was saved."
      : `Answer saved with ${data.sources.length} verified ${
          data.sources.length === 1 ? "source" : "sources"
        }.`;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      answerStatus.classList.remove("error-message");
      answerStatus.textContent = "Grounded answer request cancelled.";
    } else {
      const message =
        error instanceof Error ? error.message : "The request failed.";
      showFormError(answerStatus, message);
    }
  } finally {
    activeAnswerRequest = null;
    setAnswerBusy(false);
  }
});

syncModelOptions(answerProvider, answerModel);

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
