import React from "react";
import { ScrollView, StyleSheet } from "react-native";
import { router } from "expo-router";
import RestBreakScreen from "../RestBreakScreen";
import { PrimaryButton } from "../../components/MiSenderoUI";
import { resumeRouteSession } from "../../../services/routeSession";

const renderer = require("react-test-renderer");

jest.mock("expo-router", () => ({
  router: { push: jest.fn(), dismissTo: jest.fn() },
  useLocalSearchParams: () => ({ id: "7", startedAt: "100000", totalMeters: "5000", routeProgressMeters: "800" }),
  useFocusEffect: jest.fn(),
}));
jest.mock("@expo/vector-icons", () => ({ Ionicons: () => null }));
jest.mock("react-native-safe-area-context", () => ({
  SafeAreaView: require("react-native").View,
}));
jest.mock("../../../services/trailRepository", () => ({
  getTrailById: jest.fn().mockResolvedValue({ id: 7, name: "Sendero de prueba", distance_km: 5 }),
}));
jest.mock("../../../services/routeSession", () => ({
  activeRouteSeconds: jest.fn().mockReturnValue(600),
  getRouteSession: jest.fn().mockResolvedValue({ state: "paused" }),
  pauseRouteSession: jest.fn().mockResolvedValue(undefined),
  resumeRouteSession: jest.fn().mockResolvedValue(undefined),
}));
jest.mock("../../../services/routeTracking", () => ({
  getRouteTrackingSummary: jest.fn().mockResolvedValue({ distanceMeters: 800 }),
}));
jest.mock("../../../services/wearableMetrics", () => ({
  getWearableRuntimeStatus: jest.fn().mockResolvedValue(null),
}));

let screen: ReturnType<typeof renderer.create>;

beforeEach(async () => {
  jest.clearAllMocks();
  await renderer.act(async () => {
    screen = renderer.create(<RestBreakScreen />);
  });
}, 15000);

afterEach(async () => {
  await renderer.act(async () => screen.unmount());
});

test("places both route actions inside a bounded vertical scroll view", () => {
  const scroll = screen.root.findByType(ScrollView);
  expect(scroll.props.testID).toBe("paused-route-scroll");
  expect(scroll.props.scrollEnabled).not.toBe(false);
  expect(scroll.props.horizontal).not.toBe(true);
  expect(StyleSheet.flatten(scroll.props.style)).toMatchObject({ flex: 1, minHeight: 0 });
  expect(StyleSheet.flatten(scroll.props.contentContainerStyle)).toMatchObject({ flexGrow: 1, paddingBottom: 24 });
  expect(scroll.findAllByType(PrimaryButton).map((button: { props: { label: string } }) => button.props.label)).toEqual([
    "Reanudar recorrido", "Finalizar y guardar",
  ]);
});

test("finalizing from the scroll view preserves recorded route data", async () => {
  const buttons = screen.root.findByType(ScrollView).findAllByType(PrimaryButton);
  await renderer.act(async () => buttons[1].props.onPress());
  expect(router.push).toHaveBeenCalledWith({
    pathname: "/recorrido-finalizado",
    params: { id: "7", startedAt: "100000", traveledMeters: "800", routeProgressMeters: "800", totalMeters: "5000" },
  });
});

test("resuming still returns to the active route with the same session", async () => {
  const buttons = screen.root.findByType(ScrollView).findAllByType(PrimaryButton);
  await renderer.act(async () => buttons[0].props.onPress());
  expect(resumeRouteSession).toHaveBeenCalledWith(7, 100000);
  expect(router.dismissTo).toHaveBeenCalledWith({
    pathname: "/route-map", params: { active: "1", id: "7", startedAt: "100000" },
  });
});
