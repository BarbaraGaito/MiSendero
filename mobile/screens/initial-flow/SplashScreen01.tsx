import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { colors } from "../../components/MiSenderoUI";

export default function SplashScreen01() {
  return (
    <SafeAreaView edges={["top", "bottom"]} style={styles.safeArea}>
      <View style={styles.content}>
        <View style={styles.center}>
          <View style={styles.logo}>
            <Ionicons name="leaf-outline" size={54} color={colors.white} />
          </View>
          <Text style={styles.brand}>MiSendero</Text>
          <Text style={styles.subtitle}>
            Rutas, mapas offline y seguridad para salir a caminar con mas confianza.
          </Text>
        </View>

        <View style={styles.loader}>
          <View style={styles.loaderTrack}>
            <View style={styles.loaderFill} />
          </View>
          <Text style={styles.loadingText}>Cargando rutas cercanas...</Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: colors.primaryDark,
    flex: 1,
  },
  content: {
    flex: 1,
    paddingBottom: 38,
    paddingHorizontal: 22,
    paddingTop: 34,
  },
  center: {
    alignItems: "center",
    flex: 1,
    justifyContent: "center",
    paddingHorizontal: 12,
    transform: [{ translateY: 18 }],
  },
  logo: {
    alignItems: "center",
    backgroundColor: colors.primary,
    borderColor: "rgba(255,255,255,0.22)",
    borderRadius: 40,
    borderWidth: 1,
    height: 96,
    justifyContent: "center",
    width: 96,
  },
  brand: {
    color: colors.white,
    fontSize: 38,
    fontWeight: "900",
    marginTop: 22,
  },
  subtitle: {
    color: "#DCEBE0",
    fontSize: 16,
    lineHeight: 23,
    marginTop: 12,
    maxWidth: 310,
    textAlign: "center",
  },
  loader: {
    alignItems: "center",
    paddingBottom: 18,
  },
  loaderTrack: {
    backgroundColor: "rgba(255,255,255,0.24)",
    borderRadius: 999,
    height: 8,
    overflow: "hidden",
    width: 180,
  },
  loaderFill: {
    backgroundColor: colors.white,
    borderRadius: 999,
    height: "100%",
    width: "72%",
  },
  loadingText: {
    color: "#DCEBE0",
    fontSize: 13,
    fontWeight: "700",
    marginTop: 12,
  },
});
