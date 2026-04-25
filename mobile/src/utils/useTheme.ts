import { useStore } from "../state/store";
import { getTheme, type Theme } from "./theme";

export function useTheme(): Theme {
  const { state } = useStore();
  return getTheme(state.themeName);
}
