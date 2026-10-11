import { useState } from "react";
import { DataModeContext } from "./dataMode";

export default function DataModeProvider({ children }) {
  const [mode, setMode] = useState(() => {
    const saved = sessionStorage.getItem("fairworth-data-mode");
    return (saved ?? import.meta.env.VITE_DATA_MODE) === "provider"
      ? "provider"
      : "demo";
  });
  function changeMode(next) {
    if (!["demo", "provider"].includes(next)) return;
    sessionStorage.setItem("fairworth-data-mode", next);
    setMode(next);
  }
  return (
    <DataModeContext.Provider value={{ mode, setMode: changeMode }}>
      {children}
    </DataModeContext.Provider>
  );
}
