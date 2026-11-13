import { Platform, type ViewStyle } from "react-native";

const useNativeElevation = Platform.OS === "android" && Platform.Version < 28;

export const surfaceShadows = {
  card: useNativeElevation
    ? { elevation: 2 }
    : { boxShadow: "0 2px 5px rgba(20, 36, 28, 0.04), 0 5px 16px rgba(20, 36, 28, 0.07)" },
  floating: useNativeElevation
    ? { elevation: 4 }
    : { boxShadow: "0 2px 6px rgba(20, 36, 28, 0.06), 0 6px 20px rgba(20, 36, 28, 0.11)" },
} satisfies Record<string, ViewStyle>;
