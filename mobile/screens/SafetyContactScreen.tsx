import * as Network from "expo-network";
import { router, useLocalSearchParams } from "expo-router";
import React, { useEffect, useMemo, useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  getEmergencyContact,
  saveEmergencyContact,
} from "../../services/emergencyContact";
import {
  Card,
  PrimaryButton,
  ScreenShell,
  ScreenTitle,
  TopBar,
  colors,
} from "../components/MiSenderoUI";

export default function SafetyContactScreen() {
  const insets = useSafeAreaInsets();
  const { id, returnTo } = useLocalSearchParams<{
    id?: string;
    returnTo?: string;
  }>();
  const trailId = Number(id) || 1;
  const openedFromTrailStart = returnTo === "trail-start";
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [relationship, setRelationship] = useState("");
  const [isOnline, setIsOnline] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const canSave = useMemo(
    () => name.trim().length > 2 && phone.trim().length > 5 && relationship.trim().length > 1,
    [name, phone, relationship]
  );

  useEffect(() => {
    let isMounted = true;

    Promise.all([
      getEmergencyContact(),
      Network.getNetworkStateAsync().catch(() => null),
    ])
      .then(([contact, networkState]) => {
        if (!isMounted) return;

        if (contact) {
          setName(contact.name);
          setPhone(contact.phone);
          setRelationship(contact.relationship);
        }

        setIsOnline(
          Boolean(networkState?.isConnected) &&
            networkState?.isInternetReachable !== false
        );
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const goBackAfterSave = () => {
    if (openedFromTrailStart) {
      router.push({
        pathname: "/trail-start",
        params: { id: String(trailId) },
      });
      return;
    }

    router.push("/perfil");
  };

  const handleSave = async () => {
    if (!canSave || isSaving) {
      setMessage("Completa nombre, telefono y vinculo para guardar el contacto.");
      return;
    }

    setIsSaving(true);
    setMessage(null);

    try {
      await saveEmergencyContact({ name, phone, relationship });
      goBackAfterSave();
    } catch (error) {
      setMessage("No pudimos guardar el contacto de emergencia.");
    } finally {
      setIsSaving(false);
    }
  };

  const goBack = () => {
    if (openedFromTrailStart) {
      router.push({
        pathname: "/trail-start",
        params: { id: String(trailId) },
      });
      return;
    }

    router.push("/perfil");
  };

  return (
    <ScreenShell
      footer={
        <View style={[styles.stickyFooter, { paddingBottom: Math.max(16, insets.bottom + 10) }]}>
          <PrimaryButton
            label={isLoading ? "Cargando" : isSaving ? "Guardando" : "Guardar contacto"}
            icon="shield-checkmark-outline"
            onPress={handleSave}
          />
        </View>
      }
    >
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={styles.keyboardView}
      >
        <TopBar title="Contacto de seguridad" onBack={goBack} />
        <ScrollView
          bounces
          contentContainerStyle={[
            styles.scrollContent,
            { paddingBottom: 28 },
          ]}
          keyboardShouldPersistTaps="handled"
          nestedScrollEnabled
          showsVerticalScrollIndicator={false}
          style={styles.scrollView}
        >
          <ScreenTitle
            eyebrow="Contacto de seguridad"
            title="Contacto de seguridad"
            subtitle="Esta persona queda disponible para tus alertas SOS durante el recorrido."
          />

          <Card tone={isOnline ? "default" : "orange"}>
            <Text style={styles.cardTitle}>
              {isOnline ? "Datos del contacto" : "Modo sin conexion"}
            </Text>
            <Text style={styles.cardText}>
              {isOnline
                ? "Guardalo antes de iniciar una ruta para habilitar SOS y tenerlo listo en el dispositivo."
                : "Podes guardar o consultar el contacto localmente; se usara para SOS aunque no tengas senal."}
            </Text>
          </Card>

          <Card>
            <Text style={styles.label}>Nombre completo</Text>
            <TextInput
              autoCapitalize="words"
              onChangeText={setName}
              placeholder="Ej: Ayelen Mendoza"
              placeholderTextColor={colors.muted}
              returnKeyType="next"
              style={styles.input}
              value={name}
            />

            <Text style={styles.label}>Telefono</Text>
            <TextInput
              keyboardType="phone-pad"
              onChangeText={setPhone}
              placeholder="+54 9 11 5555 5555"
              placeholderTextColor={colors.muted}
              style={styles.input}
              value={phone}
            />

            <Text style={styles.label}>Vinculo</Text>
            <TextInput
              autoCapitalize="sentences"
              onChangeText={setRelationship}
              placeholder="Familiar, amistad, pareja..."
              placeholderTextColor={colors.muted}
              returnKeyType="done"
              style={styles.input}
              value={relationship}
            />
          </Card>

          <Card tone="green">
            <Text style={styles.cardTitle}>Uso de datos</Text>
            <Text style={styles.cardText}>
              MiSendero usa este contacto solo para seguridad. Se guarda una copia
              local para poder consultarlo durante una salida sin internet.
            </Text>
          </Card>

          {message ? <Text style={styles.messageText}>{message}</Text> : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  keyboardView: {
    flex: 1,
    minHeight: 0,
  },
  scrollContent: {
    flexGrow: 1,
  },
  scrollView: {
    flex: 1,
    minHeight: 0,
  },
  label: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "800",
    marginBottom: 8,
  },
  input: {
    backgroundColor: colors.page,
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    color: colors.ink,
    fontSize: 14,
    height: 48,
    marginBottom: 14,
    paddingHorizontal: 12,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "800",
  },
  cardText: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 20,
    marginTop: 4,
  },
  messageText: {
    color: colors.danger,
    fontSize: 13,
    fontWeight: "800",
    marginTop: 8,
  },
  stickyFooter: {
    backgroundColor: colors.softer,
    paddingHorizontal: 22,
    paddingTop: 10,
  },
});
