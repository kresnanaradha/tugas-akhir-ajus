import { useState } from "react";

// idle -> loading -> done/error untuk apa pun yang memanggil pipeline backend (upload) dan menunggu hasilnya
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
