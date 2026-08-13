const form = document.querySelector("#generation-form");
const providerSelect = document.querySelector("#provider");
const modelSelect = document.querySelector("#model");
const promptInput = document.querySelector("#prompt");
const promptCount = document.querySelector("#prompt-count");
const submitButton = document.querySelector("#generate-button");
const buttonLabel = submitButton.querySelector(".button-label");
const buttonProgress = submitButton.querySelector(".button-progress");
const formStatus = document.querySelector("#form-status");
const resultPanel = document.querySelector("#result");

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
}

function renderResult(data) {
  resultFields.provider.textContent = data.provider;
  resultFields.text.textContent = data.text || "The provider returned no text.";
  resultFields.model.textContent = data.model;
  resultFields.latency.textContent = `${data.latency_ms.toFixed(2)} ms`;
  resultFields.inputTokens.textContent = data.input_tokens;
  resultFields.outputTokens.textContent = data.output_tokens;
  resultFields.finishReason.textContent = data.finish_reason;
  resultFields.requestId.textContent = data.request_id;
  resultFields.providerRequestId.textContent =
    data.provider_request_id || "Not supplied";
  resultPanel.hidden = false;
}

providerSelect.addEventListener("change", syncModelOptions);

promptInput.addEventListener("input", () => {
  promptCount.textContent = `${promptInput.value.length} / ${promptInput.maxLength}`;
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
  formStatus.textContent = "Waiting for the selected provider…";
  setBusy(true);

  try {
    const response = await fetch("/api/generate", {
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
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error?.message || "The request failed safely.");
    }

    renderResult(data);
    formStatus.textContent = "Response completed.";
  } catch (error) {
    const message = error instanceof Error ? error.message : "The request failed.";
    showError(message);
  } finally {
    setBusy(false);
  }
});

syncModelOptions();
