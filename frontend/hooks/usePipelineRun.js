import { useState } from "react";

// Shared idle -> loading -> done/error state machine for anything that
// calls the meeting-bot pipeline (upload or join) and waits on the result.
// See lib/api.js for the actual fetch calls and components/PipelineResult.jsx
// for how the result shape gets rendered.
export function usePipelineRun(runFn) {
  const [status, setStatus] = useState("idle"); // idle | loading | error | done
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function run(...args) {
    setStatus("loading");
    setError("");
    try {
      const data = await runFn(...args);
      setResult(data);
      setStatus("done");
    } catch (e) {
      setError(e.message || "Terjadi kesalahan");
      setStatus("error");
    }
  }

  function reset() {
    setStatus("idle");
    setResult(null);
    setError("");
  }

  return { status, result, error, run, reset };
}
