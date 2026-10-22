import * as Network from "expo-network";
import { useEffect, useState } from "react";
import { StyleSheet, Text } from "react-native";
import { Card, colors } from "./MiSenderoUI";

// Internet and mobile coverage are different things: the phone can report Wi-Fi/data state, but an
// app cannot measure cell coverage, so it says so instead of guessing.
export const internetStatusText = (state: { isConnected?: boolean; isInternetReachable?: boolean } | null) =>
  !state ? "Internet: no pudimos comprobarlo."
    : state.isConnected && state.isInternetReachable !== false ? "Internet: hay conexión."
      : "Internet: sin conexión. Eso no significa que no haya cobertura celular para SMS o llamadas.";

export function SosConnectivityNotice() {
  const [state, setState] = useState<{ isConnected?: boolean; isInternetReachable?: boolean } | null>(null);
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => Network.getNetworkStateAsync()).then((value) => { if (active) setState(value ?? null); }).catch(() => undefined);
    return () => { active = false; };
  }, []);
  return (
    <Card>
      <Text style={styles.title}>Conexión</Text>
      <Text style={styles.body}>{internetStatusText(state)}</Text>
      <Text style={styles.body}>Cobertura celular: MiSendero no puede medirla. Si el SMS o la llamada no salen, probá moverte a un punto más alto o abierto.</Text>
    </Card>
  );
}

const styles = StyleSheet.create({
  title: { color: colors.ink, fontSize: 17, fontWeight: "800" },
  body: { color: colors.muted, fontSize: 14, lineHeight: 21, marginTop: 8 },
});
