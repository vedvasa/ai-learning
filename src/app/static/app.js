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

function syncModelOptions() {
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

function setBusy(isBusy) {
  submitButton.disabled = isBusy;
  providerSelect.disabled = isBusy;
  modelSelect.disabled = isBusy;
  promptInput.disabled = isBusy;
  cancelButton.hidden = !isBusy;
  buttonLabel.hidden = isBusy;
  buttonProgress.hidden = !isBusy;
}

function createRequestId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }

  return `browser-${Date.now()}`;
}

function showError(message) {
  formStatus.textContent = message;
  formStatus.classList.add("error-message");
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

providerSelect.addEventListener("change", syncModelOptions);

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
    showError("Enter a prompt before generating a response.");
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
      const data = await response.json();
      throw new Error(data.error?.message || "The request failed safely.");
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
      showError(message);
    }
  } finally {
    activeRequest = null;
    setBusy(false);
  }
});

syncModelOptions();
