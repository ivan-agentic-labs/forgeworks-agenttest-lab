(() => {
  "use strict";

  const terminalStatuses = new Set(["MISSING", "TIMEOUT", "INVALID_RESULT"]);
  const validStatuses = new Set(["PASS", "FAIL", "MISSING", "TIMEOUT", "INVALID_RESULT"]);
  const $ = (id) => document.getElementById(id);
  const logLines = [];

  function apiBase() {
    const configured = $("api-base").value.trim();
    return (configured || window.location.origin).replace(/\/$/, "");
  }

  function appendLog(message, payload) {
    logLines.push(`${new Date().toISOString()} ${message}${payload === undefined ? "" : `\n${JSON.stringify(payload, null, 2)}`}`);
    $("log").textContent = logLines.join("\n\n");
  }

  function setVerdict(state, summary, verdict) {
    const pill = $("verdict-pill");
    pill.className = `pill ${state}`;
    pill.textContent = verdict || state.toUpperCase();
    $("verdict-summary").textContent = summary;
  }

  function idempotencyKey(label) {
    return `web-console-${label}-${crypto.randomUUID()}`;
  }

  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    const token = $("token").value.trim();
    if (!token) throw new Error("A scoped bearer token is required before calling the API.");
    headers.set("Authorization", `Bearer ${token}`);
    if (options.body) {
      headers.set("Content-Type", "application/json");
      headers.set("Idempotency-Key", options.idempotencyKey || idempotencyKey(path));
    }
    let response;
    try {
      response = await fetch(`${apiBase()}${path}`, { ...options, headers });
    } catch (error) {
      throw new Error(`API unavailable: ${error.message}`);
    }
    const text = await response.text();
    let body;
    try { body = text ? JSON.parse(text) : null; } catch { body = { detail: text }; }
    appendLog(`${options.method || "GET"} ${path} -> ${response.status}`, body);
    if (!response.ok) {
      const detail = body && typeof body === "object" ? (body.detail || body.title || JSON.stringify(body)) : String(body);
      throw new Error(`${response.status}: ${detail}`);
    }
    return body;
  }

  function parseStatuses(raw, label) {
    const statuses = raw.split(",").map((status) => status.trim().toUpperCase()).filter(Boolean);
    if (!statuses.length) throw new Error(`${label} needs at least one case status.`);
    const invalid = statuses.filter((status) => !validStatuses.has(status));
    if (invalid.length) throw new Error(`${label} contains unsupported status: ${invalid.join(", ")}`);
    return statuses;
  }

  function caseResults(statuses) {
    return statuses.map((status, index) => ({
      case_key: window.forgeUploadedArtifact?.caseKeys?.[index] || `case-${index + 1}`,
      status,
      ...(status === "PASS" ? { score: 1 } : status === "FAIL" ? { score: 0 } : {})
    }));
  }

  function sha(char) { return char.repeat(64); }

  function assertResponseFields(body, fields, label) {
    const missing = fields.filter((field) => body == null || body[field] === undefined || body[field] === null || body[field] === "");
    if (missing.length) throw new Error(`${label} is incomplete; missing ${missing.join(", ")}. Decision blocked fail-closed.`);
  }

  function renderCases(label, items) {
    const root = $("case-results");
    for (const item of items || []) {
      const row = document.createElement("div");
      row.className = "case-row";
      const key = document.createElement("span");
      key.className = "case-key";
      key.textContent = `${label} / ${item.case_key || "unknown-case"}`;
      const status = document.createElement("span");
      const grade = String(item.grade_status || "INVALID_RESULT").toUpperCase();
      status.className = `status ${terminalStatuses.has(grade) || grade === "FAIL" ? "fail" : "pass"}`;
      status.textContent = grade;
      row.append(key, status);
      root.append(row);
    }
  }

  function renderBinding(verdict) {
    const binding = $("binding");
    binding.replaceChildren();
    const values = {
      "Comparison ID": verdict.comparison_id,
      "Dataset version": verdict.binding && verdict.binding.dataset_version_id,
      "Baseline run": verdict.binding && verdict.binding.baseline_run_id,
      "Candidate run": verdict.binding && verdict.binding.candidate_run_id,
      "Policy": verdict.policy_version,
      "Artifact SHA-256": verdict.signed_artifact_sha256
    };
    for (const [label, value] of Object.entries(values)) {
      const wrapper = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = label;
      dd.textContent = value == null ? "MISSING" : String(value);
      wrapper.append(dt, dd);
      binding.append(wrapper);
    }
    binding.hidden = false;
  }

  function evaluateFailClosed(verdict, comparison, baselineCases, candidateCases) {
    assertResponseFields(comparison, ["id", "missing_case_count", "candidate_run_id", "baseline_run_id"], "Comparison response");
    assertResponseFields(verdict, ["comparison_id", "verdict", "policy_version", "signed_artifact_sha256", "binding"], "Verdict response");
    const observed = [...(baselineCases.items || []), ...(candidateCases.items || [])];
    const statuses = observed.map((item) => String(item.grade_status || "INVALID_RESULT").toUpperCase());
    const terminal = statuses.filter((status) => terminalStatuses.has(status));
    const missingCount = Number(comparison.missing_case_count);
    if (!Number.isFinite(missingCount) || missingCount !== 0 || terminal.length) {
      return { state: "fail", label: "FAIL / FAIL-CLOSED", summary: `The API returned an unsafe evaluation: ${terminal.length ? terminal.join(", ") : "missing case coverage"}. A pass is not possible.` };
    }
    if (verdict.verdict !== "PASS") {
      return { state: "fail", label: `FAIL / ${verdict.verdict || "INVALID"}`, summary: "The signed API verdict is not PASS. The console preserves the failure." };
    }
    return { state: "pass", label: "PASS", summary: "Signed PASS: complete case coverage and no fail-closed terminal statuses were observed." };
  }

  async function runFlow() {
    const button = $("run-flow");
    button.disabled = true;
    $("case-results").replaceChildren();
    $("binding").hidden = true;
    setVerdict("blocked", "Working. A missing or invalid API response will block the decision fail-closed.", "RUNNING");
    try {
      const baselineStatuses = parseStatuses($("baseline-statuses").value, "Baseline statuses");
      const candidateStatuses = parseStatuses($("candidate-statuses").value, "Candidate statuses");
      const threshold = Number($("threshold").value);
      if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1) throw new Error("Threshold must be between 0 and 1.");
      const uploaded = window.forgeUploadedArtifact;
      if (window.forgeAuthConfig?.environment === "staging" && !uploaded) throw new Error("Unggah dataset JSONL terlebih dahulu.");
      if (uploaded && (baselineStatuses.length !== uploaded.caseKeys.length || candidateStatuses.length !== uploaded.caseKeys.length)) throw new Error("Jumlah hasil baseline dan kandidat harus sama dengan jumlah kasus dataset.");
      const dataset = await request("/v1/datasets", { method: "POST", body: JSON.stringify({ name: $("dataset-name").value.trim() }) });
      assertResponseFields(dataset, ["id"], "Dataset response");
      const version = await request(`/v1/datasets/${dataset.id}/versions`, { method: "POST", body: JSON.stringify({ artifact_id: $("artifact-id").value.trim(), sha256: uploaded?.sha256 || sha("a"), case_count: uploaded?.caseKeys.length || Math.max(baselineStatuses.length, candidateStatuses.length) }) });
      assertResponseFields(version, ["id"], "Dataset version response");
      const build = await request("/v1/agent-builds", { method: "POST", body: JSON.stringify({ name: $("build-name").value.trim(), build_sha256: sha("b"), tool_manifest_sha256: sha("c"), prompt_version: "web-console-v1" }) });
      assertResponseFields(build, ["id"], "Build response");
      const runPayload = (statuses) => JSON.stringify({ dataset_version_id: version.id, agent_build_id: build.id, grader_sha256: sha("d"), grader_config: { threshold, seed: 42, seed_source: "web-console-fixture" }, case_results: caseResults(statuses) });
      const baseline = await request("/v1/evaluation-runs", { method: "POST", body: runPayload(baselineStatuses) });
      assertResponseFields(baseline, ["id"], "Baseline run response");
      const candidate = await request("/v1/evaluation-runs", { method: "POST", body: runPayload(candidateStatuses) });
      assertResponseFields(candidate, ["id"], "Candidate run response");
      const comparison = await request(`/v1/evaluation-runs/${candidate.id}/comparisons`, { method: "POST", body: JSON.stringify({ baseline_run_id: baseline.id, policy_version: $("policy-version").value.trim(), threshold }) });
      const baselineCases = await request(`/v1/evaluation-runs/${baseline.id}/cases`);
      const candidateCases = await request(`/v1/evaluation-runs/${candidate.id}/cases`);
      renderCases("baseline", baselineCases.items);
      renderCases("candidate", candidateCases.items);
      const verdict = await request(`/v1/comparisons/${comparison.id}/ci-verdict`);
      const decision = evaluateFailClosed(verdict, comparison, baselineCases, candidateCases);
      setVerdict(decision.state, decision.summary, decision.label);
      renderBinding(verdict);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      appendLog("DECISION BLOCKED", { error: message });
      setVerdict("blocked", `${message} No PASS is emitted when evidence is missing, timed out, invalid, or unavailable.`, "BLOCKED / FAIL-CLOSED");
    } finally {
      button.disabled = false;
    }
  }

  $("run-flow").addEventListener("click", runFlow);
  $("clear-log").addEventListener("click", () => {
    logLines.length = 0;
    $("log").textContent = "Waiting for an evaluation flow.";
    $("case-results").replaceChildren();
  });
  $("api-base").value = window.location.origin === "null" ? "http://127.0.0.1:8000" : window.location.origin;
})();
