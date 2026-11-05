// Native boundaries only. Product screens and UI components remain real.
import { AppState } from "react-native";
Object.defineProperty(AppState, "currentState", { configurable: true, writable: true, value: "active" });
jest.mock("@expo/vector-icons", () => ({ Ionicons: "Icon" }));
jest.mock("react-native-safe-area-context", () => ({
  SafeAreaView: require("react-native").View,
  SafeAreaProvider: require("react-native").View,
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));
jest.mock("expo-router", () => ({
  router: { push: jest.fn(), navigate: jest.fn(), replace: jest.fn(), back: jest.fn(), canGoBack: jest.fn(() => true), setParams: jest.fn() },
  useLocalSearchParams: jest.fn(() => ({ id: "7", startedAt: "1791626400000" })),
  useFocusEffect: (effect: () => void | (() => void)) => require("react").useEffect(effect, [effect]),
  Stack: require("react-native").View,
}));
jest.mock("expo-linking", () => ({ openURL: jest.fn().mockResolvedValue(true), createURL: (path: string) => `misendero://${path}` }));
