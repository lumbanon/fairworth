import { useDataMode } from "@/context/dataMode";

export default function DataModeControl() {
  const { mode, setMode } = useDataMode();
  return (
    <div className="research-data-mode">
      <div>
        <strong>Financial data</strong>
        <p>
          {mode === "demo"
            ? "Fictional demonstration datasets"
            : "Provider-backed data · freshness shown with each source"}
        </p>
      </div>
      <div
        className="research-segmented"
        role="group"
        aria-label="Financial data mode"
      >
        <button aria-pressed={mode === "demo"} onClick={() => setMode("demo")}>
          Demonstration
        </button>
        <button
          aria-pressed={mode === "provider"}
          onClick={() => setMode("provider")}
        >
          Provider data
        </button>
      </div>
    </div>
  );
}
