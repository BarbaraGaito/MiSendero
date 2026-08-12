import React from "react";
import { router, useLocalSearchParams } from "expo-router";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import {
  InfoCard,
  PrimaryButton,
  ScreenShell,
  TopBar,
  colors,
} from "../components/MiSenderoUI";

const checklist = [
  "Agua suficiente",
  "Mapa descargado",
  "Batería mayor al 60%",
  "Aviso de salida enviado",
];

export default function Screen05TrailStart() {
  const insets = useSafeAreaInsets();
  const { id } = useLocalSearchParams<{ id?: string }>();

  return (
    <ScreenShell>
      <TopBar title="Antes de salir" onBack={() => router.back()} />

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scroll}>
        <View style={styles.statusCircle}>
          <Ionicons name="checkmark" size={48} color={colors.green} />
        </View>
        <Text style={styles.title}>Todo listo para comenzar</Text>
        <Text style={styles.subtitle}>
          Confirmá los últimos puntos de seguridad y empezá el recorrido.
        </Text>

        <InfoCard style={styles.card}>
          <Text style={styles.cardTitle}>Checklist rápido</Text>
          {checklist.map((item) => (
            <View key={item} style={styles.row}>
              <Ionicons name="checkmark-circle" size={22} color={colors.green} />
              <Text style={styles.rowText}>{item}</Text>
            </View>
          ))}
        </InfoCard>

        <InfoCard style={styles.warning}>
          <Ionicons name="alert-circle-outline" size={24} color={colors.danger} />
          <View style={styles.warningText}>
            <Text style={styles.warningTitle}>Recordatorio</Text>
            <Text style={styles.warningBody}>
              Si cambia el clima o baja la luz, volvé al punto de inicio.
            </Text>
          </View>
        </InfoCard>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: Math.max(20, insets.bottom + 14) }]}>
        <PrimaryButton
          label="Comenzar ahora"
          icon="play-outline"
          onPress={() =>
            router.push({
              pathname: "/route-map",
              params: { active: "1", id: id || "1" },
            })
          }
        />
      </View>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  scroll: {
    alignItems: "center",
    paddingBottom: 118,
  },
  statusCircle: {
    alignItems: "center",
    backgroundColor: colors.mint,
    borderRadius: 54,
    height: 108,
    justifyContent: "center",
    marginTop: 14,
    width: 108,
  },
  title: {
    color: colors.ink,
    fontSize: 31,
    fontWeight: "900",
    lineHeight: 37,
    marginTop: 22,
    textAlign: "center",
  },
  subtitle: {
    color: colors.muted,
    fontSize: 16,
    lineHeight: 23,
    marginTop: 10,
    textAlign: "center",
  },
  card: {
    alignSelf: "stretch",
    marginTop: 26,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
    marginBottom: 12,
  },
  row: {
    alignItems: "center",
    borderTopColor: colors.line,
    borderTopWidth: 1,
    flexDirection: "row",
    gap: 10,
    paddingVertical: 13,
  },
  rowText: {
    color: colors.ink,
    fontSize: 15,
    fontWeight: "700",
  },
  warning: {
    alignItems: "center",
    alignSelf: "stretch",
    backgroundColor: "#FFF4F2",
    flexDirection: "row",
    gap: 12,
    marginTop: 16,
  },
  warningText: {
    flex: 1,
  },
  warningTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "900",
  },
  warningBody: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
    marginTop: 3,
  },
  footer: {
    backgroundColor: colors.softer,
    bottom: 0,
    left: 0,
    padding: 22,
    paddingBottom: 28,
    position: "absolute",
    right: 0,
  },
});
