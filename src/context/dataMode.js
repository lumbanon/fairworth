import { createContext, useContext } from "react";

export const DataModeContext = createContext({
  mode: "demo",
  setMode: () => {},
});
export function useDataMode() {
  return useContext(DataModeContext);
}
