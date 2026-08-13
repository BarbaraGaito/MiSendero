import * as Network from "expo-network";
import { router, useLocalSearchParams } from "expo-router";
import React, { useEffect, useMemo, useState } from "react";
import { StyleSheet, Text, TextInput, View } from "react-native";
import {
  getEmergencyContact,
  saveEmergencyContact,
} from "../../services/emergencyContact";
import { AppScreen, Card, PrimaryButton, ScreenTitle, colors } from "../components/MiSenderoUI";

export default function SafetyContactScreen() {
  const { id, returnTo } = useLocalSearchParams<{
    id?: string;
    returnTo?: string;
  }>();
  const trailId = Number(id) || 1;
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
    if (returnTo === "trail-start") {
      router.push({
        pathname: "/trail-start",
        params: { id: String(trailId) },
      });
      return;
    }

    router.push("/perfil");
  };

  const handleSave = async () => {
    if (!isOnline) {
      setMessage("Sin conexion: podes consultar el contacto guardado, pero no modificarlo.");
      return;
    }

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

  return (
    <AppScreen activeTab="perfil">
      <ScreenTitle
        eyebrow="Contacto de seguridad"
        title="Contacto de seguridad"
        subtitle="Esta persona recibira avisos si envias una alerta SOS."
      />

      <Card tone={isOnline ? "default" : "orange"}>
        <Text style={styles.cardTitle}>
          {isOnline ? "Datos del contacto" : "Consulta offline"}
        </Text>
        <Text style={styles.cardText}>
          {isOnline
            ? "Guarda este dato con conexion en tu cuenta antes de iniciar una ruta para habilitar SOS."
            : "Sin conexion solo se puede consultar el contacto guardado previamente para esta cuenta."}
        </Text>
      </Card>

      <Card>
        <Text style={styles.label}>Nombre completo</Text>
        <TextInput
          editable={isOnline}
          onChangeText={setName}
          placeholder="Ej: Ayelen Mendoza"
          placeholderTextColor={colors.muted}
          style={[styles.input, !isOnline && styles.inputDisabled]}
          value={name}
        />

        <Text style={styles.label}>Telefono</Text>
        <TextInput
          editable={isOnline}
          keyboardType="phone-pad"
          onChangeText={setPhone}
          placeholder="+54 9 11 5555 5555"
          placeholderTextColor={colors.muted}
          style={[styles.input, !isOnline && styles.inputDisabled]}
          value={phone}
        />

        <Text style={styles.label}>Vinculo</Text>
        <TextInput
          editable={isOnline}
          onChangeText={setRelationship}
          placeholder="Familiar, amistad, pareja..."
          placeholderTextColor={colors.muted}
          style={[styles.input, !isOnline && styles.inputDisabled]}
          value={relationship}
        />
      </Card>

      <Card tone="green">
        <Text style={styles.cardTitle}>Uso de datos</Text>
        <Text style={styles.cardText}>
          MiSendero usa este contacto solo para alertas de seguridad. Offline se
          consulta la copia local asociada al usuario actual.
        </Text>
      </Card>

      {message ? <Text style={styles.messageText}>{message}</Text> : null}

      <View style={styles.footer}>
        <PrimaryButton
          label={isLoading ? "Cargando" : isSaving ? "Guardando" : "Guardar contacto"}
          onPress={handleSave}
        />
      </View>
    </AppScreen>
  );
}

const styles = StyleSheet.create({
  label: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "800",
  },
  input: {
    backgroundColor: colors.page,
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    color: colors.ink,
    fontSize: 14,
    height: 48,
    marginBottom: 8,
    paddingHorizontal: 12,
  },
  inputDisabled: {
    opacity: 0.72,
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
  footer: {
    marginTop: "auto",
  },
});
