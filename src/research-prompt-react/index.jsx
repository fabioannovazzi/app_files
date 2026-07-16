import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";

const apiBase = `${window.location.origin.replace(/\/$/, "")}/research`;
const currentLang = window.appLanguage || "en";
const appCopy = window.appCopy || {};
const jobEndpoint = `${apiBase}/prompt/jobs`;
const POLL_DELAY_MS = 2000;
const MAX_POLL_ATTEMPTS = 150;

function readBootstrap() {
  const node = document.getElementById("researchPromptBootstrap");
  if (!node) {
    return {};
  }
  try {
    return JSON.parse(node.textContent || "{}");
  } catch (_err) {
    return {};
  }
}

const bootstrap = readBootstrap();

function t(path, fallback = "") {
  if (!path) {
    return fallback;
  }
  const value = path.split(".").reduce((acc, key) => {
    if (acc && typeof acc === "object" && key in acc) {
      return acc[key];
    }
    return undefined;
  }, appCopy);
  return typeof value === "string" ? value : fallback;
}

function toMessage(value, fallback = "") {
  if (typeof value === "string") {
    return value;
  }
  if (value === null || value === undefined) {
    return fallback;
  }
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch (_err) {
      return fallback;
    }
  }
  return String(value);
}

function copyTextToClipboard(text) {
  if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
    return navigator.clipboard.writeText(text);
  }
  return new Promise((resolve, reject) => {
    const helper = document.createElement("textarea");
    helper.value = text;
    helper.setAttribute("readonly", "");
    helper.style.position = "fixed";
    helper.style.opacity = "0";
    helper.style.pointerEvents = "none";
    helper.style.left = "-9999px";
    document.body.appendChild(helper);
    helper.focus();
    helper.select();
    try {
      const copied = document.execCommand("copy");
      document.body.removeChild(helper);
      if (!copied) {
        reject(new Error("copy_failed"));
        return;
      }
      resolve();
    } catch (err) {
      document.body.removeChild(helper);
      reject(err);
    }
  });
}

function patchPromptPosture(promptText, postureCode) {
  const postureLabel = t(`lens_values.posture.${postureCode}`, postureCode || "");
  if (!promptText || !postureLabel) {
    return promptText;
  }
  const lines = promptText.split("\n");
  for (let i = 0; i < lines.length; i += 1) {
    if (/^\s*-\s*Postura\s*:/i.test(lines[i])) {
      lines[i] = `- ${t("labels.lens_posture", "Posture")}: ${postureLabel}`;
      return lines.join("\n");
    }
    if (/^\s*-\s*Posture\s*:/i.test(lines[i])) {
      lines[i] = `- ${t("labels.lens_posture", "Posture")}: ${postureLabel}`;
      return lines.join("\n");
    }
  }
  return promptText;
}

function getFriendlyErrorMessage(defaultKey = "messages.failed") {
  return t(
    defaultKey,
    t(
      "messages.gateway_error",
      "Service is temporarily unavailable. Please try again in a few seconds.",
    ),
  );
}

async function raiseFromResponse(resp, defaultKey = "messages.failed") {
  let detail = resp.statusText;
  try {
    const data = await resp.json();
    detail = toMessage(data.detail, detail);
  } catch (_err) {
    // ignore parse errors
  }
  throw new Error(toMessage(detail, getFriendlyErrorMessage(defaultKey)));
}

function ResearchPromptApp() {
  const initialJobId = useMemo(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("job") || "";
  }, []);

  const pollTimerRef = useRef(null);
  const copyResetTimerRef = useRef(null);
  const websiteCopyResetTimerRef = useRef(null);
  const activeJobRef = useRef("");

  const [question, setQuestion] = useState("");
  const [status, setStatus] = useState({ message: "", type: "info" });
  const [isBusy, setIsBusy] = useState(false);

  const [prompt, setPrompt] = useState("");
  const [websites, setWebsites] = useState([]);
  const [lens, setLens] = useState(null);

  const [promptCopied, setPromptCopied] = useState(false);
  const [websitesCopied, setWebsitesCopied] = useState(false);

  const homeAriaLabel = t("labels.home_aria", "Return to the home page");

  const showStatus = useCallback((message, type = "info") => {
    setStatus({ message: toMessage(message, ""), type });
  }, []);

  const clearCopyResetTimer = useCallback(() => {
    if (copyResetTimerRef.current) {
      clearTimeout(copyResetTimerRef.current);
      copyResetTimerRef.current = null;
    }
  }, []);

  const clearWebsiteCopyResetTimer = useCallback(() => {
    if (websiteCopyResetTimerRef.current) {
      clearTimeout(websiteCopyResetTimerRef.current);
      websiteCopyResetTimerRef.current = null;
    }
  }, []);

  const abortActiveJob = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    activeJobRef.current = "";
  }, []);

  const renderPromptData = useCallback(
    (nextPrompt, nextWebsites = [], nextLens = null) => {
      clearCopyResetTimer();
      clearWebsiteCopyResetTimer();
      setPromptCopied(false);
      setWebsitesCopied(false);

      if (!nextPrompt) {
        setPrompt("");
        setWebsites([]);
        setLens(null);
        return;
      }
      setPrompt(nextPrompt);
      setWebsites(Array.isArray(nextWebsites) ? nextWebsites.filter((entry) => typeof entry === "string" && entry.trim()) : []);
      setLens(nextLens && typeof nextLens === "object" ? nextLens : null);
    },
    [clearCopyResetTimer, clearWebsiteCopyResetTimer],
  );

  const pollJob = useCallback(
    async (jobId, attempt = 0) => {
      if (!jobId || activeJobRef.current !== jobId) {
        return;
      }
      try {
        const resp = await fetch(`${jobEndpoint}/${jobId}?lang=${encodeURIComponent(currentLang)}`, {
          credentials: "include",
        });
        if (!resp.ok) {
          await raiseFromResponse(resp);
        }
        const data = await resp.json();

        if (jobId !== activeJobRef.current) {
          return;
        }

        if (data.status === "pending") {
          if (attempt >= MAX_POLL_ATTEMPTS) {
            abortActiveJob();
            setIsBusy(false);
            showStatus(
              t("messages.timeout", "Prompt generation is taking longer than expected. Please try again."),
              "error",
            );
            renderPromptData("", [], null);
            return;
          }
          showStatus(t("messages.generating", "Generating prompt..."));
          pollTimerRef.current = window.setTimeout(() => {
            pollJob(jobId, attempt + 1);
          }, POLL_DELAY_MS);
          return;
        }

        abortActiveJob();
        setIsBusy(false);

        if (data.status === "completed") {
          renderPromptData(data.prompt || "", data.websites || [], data.lens || null);
          if (data.prompt) {
            showStatus("");
          } else {
            showStatus(
              t("messages.empty", "The assistant returned an empty prompt. Try adjusting the question."),
              "error",
            );
          }
          return;
        }

        if (data.status === "blocked" || data.blocked) {
          showStatus(
            t("messages.flagged", "The safety checker flagged this question. Please rephrase and try again."),
            "warning",
          );
          renderPromptData("", [], null);
          return;
        }

        const errorMsg = data.error || t("messages.failed", "Prompt generation failed.");
        showStatus(errorMsg, "error");
        renderPromptData("", [], null);
      } catch (err) {
        if (jobId !== activeJobRef.current) {
          return;
        }
        abortActiveJob();
        setIsBusy(false);
        showStatus(err?.message || getFriendlyErrorMessage(), "error");
        renderPromptData("", [], null);
      }
    },
    [abortActiveJob, renderPromptData, showStatus],
  );

  const startPromptJob = useCallback(async (questionText) => {
    const resp = await fetch(`${jobEndpoint}?lang=${encodeURIComponent(currentLang)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ question: questionText }),
    });
    if (!resp.ok) {
      await raiseFromResponse(resp);
    }
    return resp.json();
  }, []);

  const resumeJob = useCallback(
    (jobId) => {
      const normalized = String(jobId || "").trim();
      if (!normalized) {
        return;
      }
      abortActiveJob();
      activeJobRef.current = normalized;
      setIsBusy(true);
      showStatus(t("messages.resuming", "Reopening your prompt request..."));
      renderPromptData("", [], null);
      pollJob(normalized, 0);
    },
    [abortActiveJob, pollJob, renderPromptData, showStatus],
  );

  useEffect(() => {
    if (!initialJobId) {
      return;
    }
    resumeJob(initialJobId);
  }, [initialJobId, resumeJob]);

  useEffect(() => {
    return () => {
      abortActiveJob();
      clearCopyResetTimer();
      clearWebsiteCopyResetTimer();
    };
  }, [abortActiveJob, clearCopyResetTimer, clearWebsiteCopyResetTimer]);

  const handleGenerate = async () => {
    const trimmedQuestion = question.trim();
    abortActiveJob();
    if (!trimmedQuestion) {
      showStatus(t("messages.enter_question", "Please enter a question before generating the prompt."), "error");
      renderPromptData("", [], null);
      return;
    }

    setIsBusy(true);
    showStatus(t("messages.submitting", "Submitting request..."));
    renderPromptData("", [], null);

    try {
      const data = await startPromptJob(trimmedQuestion);
      if (!data || !data.job_id) {
        throw new Error(t("messages.failed", "Prompt generation failed."));
      }
      activeJobRef.current = data.job_id;
      setIsBusy(false);
      showStatus(
        t(
          "messages.submitted_email",
          "Request submitted. You will receive an email when your prompt is ready.",
        ),
      );
    } catch (err) {
      abortActiveJob();
      setIsBusy(false);
      showStatus(err?.message || getFriendlyErrorMessage(), "error");
      renderPromptData("", [], null);
    }
  };

  const handlePostureSwitch = (posture) => {
    const currentPrompt = String(prompt || "").trim();
    if (!currentPrompt) {
      showStatus(
        t("messages.missing_prompt_for_posture", "Generate a prompt first, then correct posture."),
        "error",
      );
      return;
    }
    if (!posture) {
      return;
    }

    const patchedPrompt = patchPromptPosture(currentPrompt, posture);
    setPrompt(patchedPrompt);

    if (lens && typeof lens === "object") {
      setLens({ ...lens, posture, source: "user_override" });
    } else {
      setLens({
        posture,
        objective: "balanced",
        scope: "domestic_only",
        source: "user_override",
        rationale_short: "",
      });
    }

    showStatus(t("messages.posture_updated_local", "Posture updated in the prompt."));
  };

  const handleCopyPrompt = () => {
    const trimmedPrompt = String(prompt || "").trim();
    if (!trimmedPrompt) {
      showStatus(t("messages.copy_empty", "Generate a prompt before copying."), "error");
      return;
    }

    copyTextToClipboard(trimmedPrompt)
      .then(() => {
        showStatus(t("messages.copy_success", "Prompt copied to clipboard."));
        setPromptCopied(true);
        clearCopyResetTimer();
        copyResetTimerRef.current = window.setTimeout(() => setPromptCopied(false), 1600);
      })
      .catch(() => {
        showStatus(
          t("messages.copy_failed", "Unable to copy automatically. Please copy the text manually."),
          "error",
        );
      });
  };

  const websiteCsv = websites.join(", ");

  const handleCopyWebsites = () => {
    if (!websiteCsv.trim()) {
      showStatus(t("messages.copy_websites_empty", "Generate websites before copying."), "error");
      return;
    }
    copyTextToClipboard(websiteCsv)
      .then(() => {
        showStatus(t("messages.copy_websites_success", "Websites copied as comma-separated list."));
        setWebsitesCopied(true);
        clearWebsiteCopyResetTimer();
        websiteCopyResetTimerRef.current = window.setTimeout(() => setWebsitesCopied(false), 1600);
      })
      .catch(() => {
        showStatus(
          t(
            "messages.copy_websites_failed",
            "Unable to copy websites automatically. Please copy them manually.",
          ),
          "error",
        );
      });
  };

  const handleNewQuestion = () => {
    abortActiveJob();
    renderPromptData("", [], null);
    showStatus("");
  };

  const showResultPanel = Boolean(prompt);
  const showWebsitePanel = websites.length > 0;
  const postureLabel = lens?.posture
    ? t(`lens_values.posture.${lens.posture}`, lens.posture)
    : "";
  const objectiveLabel = lens?.objective
    ? t(`lens_values.objective.${lens.objective}`, lens.objective)
    : "";
  const scopeLabel = lens?.scope ? t(`lens_values.scope.${lens.scope}`, lens.scope) : "";
  const lensRationale = typeof lens?.rationale_short === "string" ? lens.rationale_short.trim() : "";
  const showLensPanel = Boolean(lens && (postureLabel || objectiveLabel || scopeLabel || lensRationale));
  const rawResultTitle = t("panels.result.title", "Structured prompt");
  const resultTitleBase = rawResultTitle
    .replace(/^\s*\d+\s*[·.\-:)\]]\s*/u, "")
    .trim() || rawResultTitle;
  const workflowSteps = [
    t("labels.workflow_steps.question", "Frame the research question clearly"),
    t("labels.workflow_steps.lens", "Infer posture, objective, and scope"),
    t("labels.workflow_steps.prompt", "Generate a reusable prompt and source domains"),
  ];
  const questionState = question.trim()
    ? (prompt ? t("labels.state.ready", "Ready") : t("labels.state.draft", "Draft"))
    : t("labels.state.none", "None yet");
  const promptState = prompt
    ? t("labels.state.ready", "Ready")
    : activeJobRef.current
      ? t("labels.state.pending", "Pending")
      : t("labels.state.none", "None yet");
  const websiteState = websites.length ? String(websites.length) : t("labels.state.none", "None yet");
  const postureState = postureLabel || (showResultPanel ? t("labels.state.auto", "Automatic") : t("labels.state.none", "None yet"));
  const summaryItems = [
    { key: "question", label: t("labels.summary.question", "Question"), value: questionState },
    { key: "prompt", label: t("labels.summary.prompt", "Prompt"), value: promptState },
    { key: "websites", label: t("labels.summary.websites", "Qualified domains"), value: websiteState },
    { key: "posture", label: t("labels.summary.posture", "Posture"), value: postureState },
  ];
  const workspaceTitle = t("panels.workspace.title", "Prompt workspace");

  return (
    <>
      <header className="landing-header">
        <a href={`/?lang=${currentLang || "en"}`} className="landing-logo-link" aria-label={homeAriaLabel}>
          <img className="landing-logo" src="https://mparanza.com/images/MPARANZA-HORIZONTAL.png" alt="Mparanza" />
        </a>
      </header>
      <main className="app-main prompt-main">
        <div className="container prompt-wrapper prompt-page">
          <h1
            className="page-title page-title--with-help"
            data-tooltip={
              t(
                "page_help",
                "Describe the research question in plain language and convert it into a structured Deep Research prompt.",
              )
            }
            aria-label={
              t(
                "page_help",
                "Describe the research question in plain language and convert it into a structured Deep Research prompt.",
              )
            }
          >
            {bootstrap.page_label || "Optimize prompt"}
          </h1>
          <p className="prompt-lead">
            {t(
              "page_help",
              "Describe the legal, tax, or compliance research task in plain language. The toolkit will frame it into a structured Deep Research prompt, infer a research posture, and propose qualified domains to prioritize.",
            )}
          </p>

          <div className="prompt-summary-strip" aria-label={workspaceTitle}>
            {summaryItems.map((item) => (
              <div className="prompt-summary-tile" key={item.key}>
                <span className="prompt-summary-tile__value">{item.value}</span>
                <span className="prompt-summary-tile__label">{item.label}</span>
              </div>
            ))}
          </div>

          <div className="prompt-layout">
            <section className="panel prompt-panel prompt-panel--input">
              <div className="panel-header">
                <h2
                  className="panel-title panel-title--with-help"
                  data-tooltip={t("panels.question.subtitle", "Describe the legal or compliance research problem you want the assistant to explore.")}
                  aria-label={t("panels.question.subtitle", "Describe the legal or compliance research problem you want the assistant to explore.")}
                >
                  {t("labels.briefing_title", "Question briefing")}
                </h2>
              </div>

              <div className="filters-subcard prompt-subcard prompt-subcard--method">
                <div className="prompt-section-kicker">
                  {t("labels.workflow_title", "Research toolkit method")}
                </div>
                <ol className="prompt-method-list">
                  {workflowSteps.map((step, index) => (
                    <li className="prompt-method-list__item" key={step}>
                      <span className="prompt-method-list__index">{index + 1}</span>
                      <span>{step}</span>
                    </li>
                  ))}
                </ol>
              </div>

              <div className="filters-subcard prompt-subcard">
                <div className="prompt-section-kicker">
                  {t("panels.question.title", "1 · Provide your question")}
                </div>
                <textarea
                  id="questionInput"
                  className="prompt-textarea"
                  rows={10}
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  aria-label={t("panels.question.title", "Provide your question")}
                  placeholder={t("labels.question_placeholder", "Enter your question...")}
                />
                <div className="actions">
                  <button
                    id="generatePrompt"
                    className="primary-button"
                    type="button"
                    disabled={isBusy}
                    onClick={handleGenerate}
                  >
                    {isBusy
                      ? t("messages.generating_button", "Generating...")
                      : t("buttons.generate_prompt", "Generate prompt")}
                  </button>
                </div>
                {status.message ? (
                  <div className="prompt-status-shell">
                    <div
                      id="promptStatus"
                      className={`status-bar${status.type === "error" ? " status-bar__error" : ""}${
                        status.type === "warning" ? " status-bar__warning" : ""
                      }`}
                    >
                      {status.message}
                    </div>
                  </div>
                ) : null}
              </div>
            </section>

            <section className="panel prompt-panel prompt-result-panel prompt-panel--workspace" id="resultPanel">
              <div className="panel-header">
                <h2>{workspaceTitle}</h2>
                <small>
                  {t(
                    "panels.workspace.subtitle",
                    "Refine the research question on the left. Review the generated prompt, research posture, and qualified domains on the right.",
                  )}
                </small>
              </div>

              {showResultPanel ? (
                <>
                {showLensPanel && (
                  <section id="lensPanel" className="filters-subcard prompt-subcard lens-subcard">
                    <h3 className="panel-subtitle">{t("panels.lens.title", "Assumed research posture")}</h3>
                    {lensRationale ? <p className="website-hint">{lensRationale}</p> : null}
                    <div className="prompt-lens-meta">
                      {postureLabel && (
                        <p className="prompt-lens-meta-item">
                          {t("labels.lens_posture", "Posture")}: {postureLabel}
                        </p>
                      )}
                      {objectiveLabel && (
                        <p className="prompt-lens-meta-item">
                          {t("labels.lens_objective", "Objective")}: {objectiveLabel}
                        </p>
                      )}
                      {scopeLabel && (
                        <p className="prompt-lens-meta-item">
                          {t("labels.lens_scope", "Scope")}: {scopeLabel}
                        </p>
                      )}
                    </div>

                    <div id="lensSwitchWrap" className="lens-switch-wrap">
                      <p className="panel-subtitle lens-switch-label">
                        {t("labels.switch_posture", "Correct posture")}
                      </p>
                      <div id="lensSwitchButtons" className="lens-switch-buttons">
                        {["planning_ex_ante", "assessment_ex_post", "defense_audit_dispute"].map((postureCode) => {
                          if (lens?.posture === postureCode) {
                            return null;
                          }
                          return (
                            <button
                              type="button"
                              className="ghost-button"
                              key={postureCode}
                              onClick={() => handlePostureSwitch(postureCode)}
                            >
                              {t(`lens_values.posture.${postureCode}`, postureCode)}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </section>
                )}

                <div className="filters-subcard prompt-subcard">
                  <div className="panel-header">
                    <h3 className="panel-subtitle">{resultTitleBase}</h3>
                  </div>
                  {status.message ? (
                    <div className="prompt-status-shell">
                      <div
                        id="promptStatus"
                        className={`status-bar${status.type === "error" ? " status-bar__error" : ""}${
                          status.type === "warning" ? " status-bar__warning" : ""
                        }`}
                      >
                        {status.message}
                      </div>
                    </div>
                  ) : null}
                  <div className="actions prompt-copy-actions">
                    <button
                      id="copyPrompt"
                      className="ghost-button prompt-copy-button icon-only-button"
                      type="button"
                      disabled={!prompt.trim()}
                      onClick={handleCopyPrompt}
                    >
                      <img src="/static/icons/copy.svg" className="prompt-copy-icon" alt="" aria-hidden="true" />
                      <span id="copyPromptLabel" className="sr-only">
                        {promptCopied
                          ? t("buttons.copied_prompt", "Copied")
                          : t("buttons.copy_prompt", "Copy prompt")}
                      </span>
                    </button>
                  </div>
                  <pre id="promptOutput" className="code-block">{prompt}</pre>
                  <p className="website-hint prompt-result-hint">
                    {t(
                      "panels.result.subtitle",
                      "Copy the generated prompt into the Deep Research assistant.",
                    )}
                  </p>
                </div>

                {showWebsitePanel && (
                  <section id="websitePanel" className="filters-subcard prompt-subcard website-panel">
                    <h3 className="panel-subtitle">{t("panels.websites.title", "Qualified websites")}</h3>
                    <div className="website-csv-wrap">
                      <div className="website-csv-header">
                        <small>
                          {t(
                            "panels.websites.csv_label",
                            "Comma-separated for OpenAI Deep Research",
                          )}
                        </small>
                        <button
                          id="copyWebsites"
                          className="ghost-button prompt-copy-button icon-only-button"
                          type="button"
                          disabled={!websiteCsv.trim()}
                          onClick={handleCopyWebsites}
                        >
                          <img src="/static/icons/copy.svg" className="prompt-copy-icon" alt="" aria-hidden="true" />
                          <span id="copyWebsitesLabel" className="sr-only">
                            {websitesCopied
                              ? t("buttons.copied_websites", "Copied websites")
                              : t("buttons.copy_websites", "Copy websites")}
                          </span>
                        </button>
                      </div>
                      <textarea
                        id="websiteCsv"
                        className="website-csv"
                        rows={2}
                        readOnly
                        value={websiteCsv}
                        aria-label={
                          t(
                            "panels.websites.csv_label",
                            "Comma-separated for OpenAI Deep Research",
                          )
                        }
                      />
                    </div>
                  </section>
                )}

                <div className="actions prompt-result-actions">
                  <button
                    type="button"
                    className="ghost-button"
                    onClick={handleNewQuestion}
                  >
                    {t("buttons.new_question", "New question")}
                  </button>
                </div>
                </>
              ) : (
                <div className="filters-subcard prompt-subcard prompt-empty-state">
                  <div className="prompt-section-kicker">
                    {workspaceTitle}
                  </div>
                  <h3>{t("panels.workspace.empty_title", "The prompt workspace will populate here")}</h3>
                  <p>
                    {t(
                      "panels.workspace.empty_body",
                      "Start with a focused question. Once the request is submitted, this area will show the structured Deep Research prompt, inferred posture, and source domains.",
                    )}
                  </p>
                </div>
              )}
            </section>
          </div>
        </div>
      </main>
    </>
  );
}

const rootNode = document.getElementById("researchPromptReactApp");
if (rootNode) {
  createRoot(rootNode).render(<ResearchPromptApp />);
}
