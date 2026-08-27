import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors } from "../../components/MiSenderoUI";
import { MiSenderoLogo } from "../../components/MiSenderoLogo";

const splashColors = {
  background: colors.primaryDark,
  brand: "#D8F0BD",
  neutral: "#DFDFDF",
};

export default function SplashScreen01() {
  return (
    <SafeAreaView edges={["top", "bottom"]} style={styles.safeArea}>
      <View style={styles.content}>
        <View style={styles.center}>
          <MiSenderoLogo markSize={104} wordmarkSize={48} />
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
    backgroundColor: splashColors.background,
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
  subtitle: {
    color: splashColors.neutral,
    fontSize: 16,
    lineHeight: 23,
    marginTop: 18,
    maxWidth: 310,
    textAlign: "center",
  },
  loader: {
    alignItems: "center",
    paddingBottom: 18,
  },
  loaderTrack: {
    backgroundColor: "rgba(223,223,223,0.28)",
    borderRadius: 999,
    height: 8,
    overflow: "hidden",
    width: 180,
  },
  loaderFill: {
    backgroundColor: splashColors.brand,
    borderRadius: 999,
    height: "100%",
    width: "72%",
  },
  loadingText: {
    color: splashColors.neutral,
    fontFamily: "BricolageGrotesque_700Bold",
    fontSize: 13,
    fontWeight: "700",
    marginTop: 12,
  },
});
