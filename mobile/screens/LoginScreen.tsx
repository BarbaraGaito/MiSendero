import React, { useState } from "react";
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { loginUser, registerUser } from "../../services/api";
import { saveAuthSession } from "../../services/authSession";
import {
  CURRENT_TERMS_VERSION,
  saveTermsAcceptance,
} from "../../services/legalConsent";
import { getExperienceProfile } from "../../services/experienceProfile";
import { colors } from "../components/MiSenderoUI";

const getFormError = (
  isRegister: boolean,
  name: string,
  email: string,
  password: string,
  acceptedTerms: boolean
) => {
  if (!email.trim() || !password.trim() || (isRegister && !name.trim())) {
    return "Completa los campos para continuar.";
  }

  if (isRegister && !acceptedTerms) {
    return "Acepta los terminos y disclaimers de seguridad para continuar.";
  }

  return null;
};

const getSubmitErrorMessage = (submitError: unknown) =>
  submitError instanceof Error ? submitError.message : "No pudimos iniciar sesion.";

export default function LoginScreen() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isRegister = mode === "register";

  const submit = async () => {
    const formError = getFormError(isRegister, name, email, password, acceptedTerms);
    if (formError) {
      setError(formError);
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const auth = isRegister
        ? await registerUser(name, email, password, CURRENT_TERMS_VERSION)
        : await loginUser(email, password);

      if (isRegister) {
        await saveTermsAcceptance(CURRENT_TERMS_VERSION);
      }

      await saveAuthSession(auth);

      if (isRegister) {
        const experienceProfile = await getExperienceProfile();
        router.replace(
          experienceProfile.completed ? "/inicio" : "/onboarding-experiencia"
        );
        return;
      }

      router.replace("/inicio");
    } catch (submitError) {
      setError(getSubmitErrorMessage(submitError));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.brand}>MiSendero</Text>
          <Text style={styles.title}>
            {isRegister ? "Crea tu cuenta" : "Bienvenida de nuevo"}
          </Text>
          <Text style={styles.subtitle}>
            Guarda tus recorridos, consulta senderos y prepara tu proxima salida.
          </Text>
        </View>

        <View style={styles.form}>
          {isRegister ? (
            <View style={styles.field}>
              <Text style={styles.label}>Nombre</Text>
              <TextInput
                value={name}
                onChangeText={setName}
                placeholder="Tu nombre"
                placeholderTextColor={colors.muted}
                style={styles.input}
              />
            </View>
          ) : null}

          <View style={styles.field}>
            <Text style={styles.label}>Email</Text>
            <TextInput
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              keyboardType="email-address"
              placeholder="tu@email.com"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
          </View>

          <View style={styles.field}>
            <Text style={styles.label}>Contrasena</Text>
            <TextInput
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              placeholder="Ingresa tu contrasena"
              placeholderTextColor={colors.muted}
              style={styles.input}
            />
          </View>

          {error ? <Text style={styles.error}>{error}</Text> : null}

          {isRegister ? (
            <View style={styles.termsBox}>
              <Pressable
                accessibilityRole="checkbox"
                accessibilityState={{ checked: acceptedTerms }}
                onPress={() => setAcceptedTerms((current) => !current)}
                style={[
                  styles.checkbox,
                  acceptedTerms && styles.checkboxChecked,
                ]}
              >
                {acceptedTerms ? (
                  <Ionicons name="checkmark" size={16} color={colors.white} />
                ) : null}
              </Pressable>
              <Text style={styles.termsText}>
                Acepto los terminos y condiciones, privacidad y disclaimers de
                seguridad.{" "}
                <Text
                  onPress={() => router.push("/terminos-condiciones")}
                  style={styles.termsLink}
                >
                  Ver terminos
                </Text>
              </Text>
            </View>
          ) : null}

          <Pressable
            disabled={isSubmitting}
            onPress={submit}
            style={[styles.primaryButton, isSubmitting && styles.disabledButton]}
          >
            <Text style={styles.primaryButtonText}>
              {isSubmitting
                ? "Un momento..."
                : isRegister
                  ? "Crear cuenta"
                  : "Iniciar sesion"}
            </Text>
          </Pressable>

          <Pressable
            onPress={() => {
              setMode(isRegister ? "login" : "register");
              setAcceptedTerms(false);
              setError(null);
            }}
            style={styles.secondaryButton}
          >
            <Text style={styles.secondaryButtonText}>
              {isRegister
                ? "Ya tengo cuenta"
                : "Crear una cuenta nueva"}
            </Text>
          </Pressable>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    backgroundColor: colors.softer,
    flex: 1,
  },
  container: {
    flex: 1,
    justifyContent: "center",
    padding: 24,
  },
  header: {
    marginBottom: 28,
  },
  brand: {
    color: colors.green,
    fontSize: 16,
    fontWeight: "900",
    marginBottom: 16,
  },
  title: {
    color: colors.ink,
    fontSize: 34,
    fontWeight: "900",
    lineHeight: 40,
  },
  subtitle: {
    color: colors.muted,
    fontSize: 15,
    lineHeight: 22,
    marginTop: 10,
  },
  form: {
    backgroundColor: colors.white,
    borderRadius: 24,
    gap: 16,
    padding: 18,
    shadowColor: "#000",
    shadowOpacity: 0.06,
    shadowRadius: 18,
  },
  field: {
    gap: 7,
  },
  label: {
    color: colors.ink,
    fontSize: 13,
    fontWeight: "800",
  },
  input: {
    backgroundColor: colors.softer,
    borderColor: colors.line,
    borderRadius: 16,
    borderWidth: 1,
    color: colors.ink,
    fontSize: 15,
    minHeight: 50,
    paddingHorizontal: 14,
  },
  error: {
    color: colors.danger,
    fontSize: 13,
    fontWeight: "700",
  },
  termsBox: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 10,
  },
  checkbox: {
    alignItems: "center",
    borderColor: colors.green,
    borderRadius: 7,
    borderWidth: 2,
    height: 24,
    justifyContent: "center",
    marginTop: 1,
    width: 24,
  },
  checkboxChecked: {
    backgroundColor: colors.green,
  },
  termsText: {
    color: colors.muted,
    flex: 1,
    fontSize: 13,
    fontWeight: "600",
    lineHeight: 19,
  },
  termsLink: {
    color: colors.green,
    fontWeight: "900",
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: colors.green,
    borderRadius: 18,
    justifyContent: "center",
    minHeight: 52,
  },
  disabledButton: {
    opacity: 0.7,
  },
  primaryButtonText: {
    color: colors.white,
    fontSize: 15,
    fontWeight: "900",
  },
  secondaryButton: {
    alignItems: "center",
    justifyContent: "center",
    minHeight: 42,
  },
  secondaryButtonText: {
    color: colors.green,
    fontSize: 14,
    fontWeight: "800",
  },
});
