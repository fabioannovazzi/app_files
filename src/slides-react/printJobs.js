const BASE_DELAY_MS = 1000;
const DELAY_STEP_MS = 250;
const MAX_DELAY_MS = 5000;

function getRetryDelay(attempt) {
  return Math.min(MAX_DELAY_MS, BASE_DELAY_MS + attempt * DELAY_STEP_MS);
}

function triggerDownload(blob, fileName) {
  const link = document.createElement("a");
  const href = URL.createObjectURL(blob);
  link.href = href;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(href);
}

export async function downloadPrintWithRetry({
  url,
  fileName,
  attempt = 0,
  onStatus,
  onFinalize,
  successMessage = "Downloaded PDF.",
  errorMessage = "PDF export failed",
  downloadErrorMessage = "Unable to download PDF.",
}) {
  let shouldFinalize = true;
  try {
    const response = await fetch(url, { credentials: "include" });
    if (response.status === 202) {
      const delay = getRetryDelay(attempt);
      setTimeout(
        () =>
          downloadPrintWithRetry({
            url,
            fileName,
            attempt: attempt + 1,
            onStatus,
            onFinalize,
            successMessage,
            errorMessage,
            downloadErrorMessage,
          }),
        delay,
      );
      shouldFinalize = false;
      return;
    }
    if (!response.ok) {
      throw new Error(downloadErrorMessage);
    }
    const blob = await response.blob();
    triggerDownload(blob, fileName);
    if (onStatus) {
      onStatus(successMessage, false);
    }
  } catch (error) {
    if (onStatus) {
      onStatus(`${errorMessage}: ${error.message}`, true);
    }
  } finally {
    if (shouldFinalize && onFinalize) {
      onFinalize();
    }
  }
}

export function pollPrintJob({
  jobId,
  pollPrint,
  fileName,
  attempt = 0,
  onStatus,
  onFinalize,
  successMessage = "Downloaded PDF.",
  errorMessage = "PDF export failed",
  downloadErrorMessage = "Unable to download PDF.",
}) {
  pollPrint(jobId)
    .then((status) => {
      const statusValue = status.status;
      if (statusValue === "succeeded" && status.downloadUrl) {
        downloadPrintWithRetry({
          url: status.downloadUrl,
          fileName,
          onStatus,
          onFinalize,
          successMessage,
          errorMessage,
          downloadErrorMessage,
        });
        return;
      }
      if (statusValue === "failed") {
        const reason = status.detail ? `: ${status.detail}` : "";
        if (onStatus) {
          onStatus(`${errorMessage}${reason}`, true);
        }
        if (onFinalize) {
          onFinalize();
        }
        return;
      }
      const delay = getRetryDelay(attempt);
      setTimeout(
        () =>
          pollPrintJob({
            jobId,
            pollPrint,
            fileName,
            attempt: attempt + 1,
            onStatus,
            onFinalize,
            successMessage,
            errorMessage,
            downloadErrorMessage,
          }),
        delay,
      );
    })
    .catch((error) => {
      if (onStatus) {
        onStatus(`${errorMessage}: ${error.message}`, true);
      }
      if (onFinalize) {
        onFinalize();
      }
    });
}
