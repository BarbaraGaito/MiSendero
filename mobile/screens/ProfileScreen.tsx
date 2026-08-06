import React from "react";
import { router } from "expo-router";
import { StyleSheet, Text, View } from "react-native";
import { AppScreen, Card, ScreenTitle, SettingRow, colors } from "../components/MiSenderoUI";

export default function ProfileScreen() {
  return (
    <AppScreen activeTab="perfil">
      <ScreenTitle
        eyebrow="Perfil y ajustes"
        title="Nombre"
        subtitle="Tu cuenta y preferencias de seguridad."
      />

      <Card tone="green">
        <View style={styles.profileRow}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>A</Text>
          </View>
          <View>
            <Text style={styles.profileName}>Nombre</Text>
            <Text style={styles.profileMeta}>3 rutas completadas • 28,6 km</Text>
          </View>
        </View>
      </Card>

      <Card>
        <Text style={styles.cardTitle}>Mapas sin conexión</Text>
        <SettingRow
          label="Sendero Laguna Esmeralda"
          value="Actualizado"
          onPress={() => router.push("/offline-mapas-descargados")}
        />
        <SettingRow
          label="Villa La Angostura"
          value="Descargar"
          onPress={() => router.push("/offline-buscar")}
        />
      </Card>

      <Card>
        <Text style={styles.cardTitle}>Seguridad y dispositivos</Text>
        <SettingRow
          label="Contacto de emergencia"
          value="Configurar"
          onPress={() => router.push("/contacto-seguridad")}
        />
        <SettingRow label="Reloj o sensor externo" value="No vinculado" />
        <SettingRow label="Modo ahorro de batería" value="Activo" />
      </Card>

      <Card>
        <Text style={styles.cardTitle}>Preferencias</Text>
        <SettingRow label="Notificaciones" value="Activadas" />
        <SettingRow label="Unidades" value="Kilómetros" />
      </Card>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  profileRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
  },
  avatar: {
    alignItems: "center",
    backgroundColor: colors.surface,
    borderRadius: 999,
    height: 52,
    justifyContent: "center",
    width: 52,
  },
  avatarText: {
    color: colors.primary,
    fontSize: 22,
    fontWeight: "900",
  },
  profileName: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "800",
  },
  profileMeta: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "600",
    marginTop: 3,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "800",
    marginBottom: 2,
  },
});
