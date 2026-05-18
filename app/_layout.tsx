import { Stack } from "expo-router";

export default function Layout() {
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: "#0B110E" },
        headerTintColor: "#F6FFF8",
        contentStyle: { backgroundColor: "#0B110E" },
      }}
    />
  );
}
