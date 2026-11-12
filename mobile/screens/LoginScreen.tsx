import { useRef, useState, type ComponentProps, type ComponentPropsWithRef, type ReactNode } from "react";
import { userMessage } from "../../services/userMessages";
import { Ionicons } from "@expo/vector-icons";
import { utf8Bytes } from "../../services/passwordPolicy";
import { router } from "expo-router";
import {
  ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView,
  StyleSheet, Text, TextInput, View, useWindowDimensions,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Svg, { Circle, Path } from "react-native-svg";
import { loginUser, registerUser } from "../../services/api";
import { saveAuthSession } from "../../services/authSession";
import { isAccountDeletionPending } from "../../services/accountLifecycle";
import {
  CURRENT_TERMS_VERSION,
  saveTermsAcceptance,
} from "../../services/legalConsent";
import { getExperienceProfile } from "../../services/experienceProfile";
import { colors, typography } from "../components/MiSenderoUI";
import { MiSenderoLogo } from "../components/MiSenderoLogo";

const getFormError = (
  isRegister: boolean,
  name: string,
  email: string,
  password: string,
  acceptedTerms: boolean
) => {
  if (!email.trim() || !password.trim() || (isRegister && !name.trim())) {
    return "Completá todos los campos para continuar.";
  }

  if (isRegister && password.length < 8) {
    return "La contraseña debe tener al menos 8 caracteres.";
  }
  if (utf8Bytes(password) > 72) return "La contraseña supera 72 bytes UTF-8. Usá una clave más corta; los acentos pueden ocupar más de un byte.";

  if (isRegister && !acceptedTerms) {
    return "Aceptá los términos y condiciones y los avisos de seguridad para continuar.";
  }

  return null;
};

const redirectAfterAuth = async (isRegister: boolean) => {
  if (!isRegister) {
    router.replace("/inicio");
    return;
  }

  const experienceProfile = await getExperienceProfile();
  router.replace(
    experienceProfile.completed ? "/inicio" : "/onboarding-experiencia"
  );
};

export default function LoginScreen() {
  const { width } = useWindowDimensions();
  const wide = width >= 840;
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const emailInput = useRef<TextInput>(null);
  const passwordInput = useRef<TextInput>(null);

  const isRegister = mode === "register";
  const buttonLabel = isRegister ? "Crear cuenta" : "Iniciar sesión";

  const submit = async () => {
    if (isSubmitting) return;
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

      // A fresh server login can restore a volatile session solely to finish a
      // pending deletion. Its persistent marker still prevents every upload.
      await saveAuthSession(auth, { deletionRetryLogin: true });
      if (await isAccountDeletionPending(auth.user.id)) {
        router.replace("/perfil");
        return;
      }
      await redirectAfterAuth(isRegister);
    } catch (submitError) {
      setError(userMessage(submitError, isRegister
        ? "No pudimos crear tu cuenta. Intentá nuevamente."
        : "No pudimos iniciar sesión. Intentá nuevamente."));
    } finally {
      setIsSubmitting(false);
    }
  };

  const update = (setter: (value: string) => void) => (value: string) => {
    setter(value);
    setError(null);
  };

  return (
    <SafeAreaView style={styles.safeArea}>
      <KeyboardAvoidingView style={styles.keyboardArea} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={[styles.scrollContent, wide && styles.scrollWide]}
          keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag">
          <View style={[styles.container, wide && styles.containerWide]}>
            <LoginBrand wide={wide} />
            <View style={[styles.formPanel, wide && styles.formPanelWide]}>
              <View style={styles.heading}>
                <Text accessibilityRole="header" style={styles.title}>
                  {isRegister ? "Creá tu cuenta" : "Iniciá sesión"}
                </Text>
                <Text style={styles.subtitle}>
                  {isRegister ? "Empezá a explorar y guardá tus recorridos en un solo lugar."
                    : "Ingresá tus datos para entrar a MiSendero."}
                </Text>
              </View>
              <View style={styles.form}>
                {isRegister ? (
                  <LoginField label="Nombre" icon="person-outline" input={{
                    autoComplete: "name", autoCapitalize: "words", value: name,
                    onChangeText: update(setName), placeholder: "Tu nombre", returnKeyType: "next",
                    submitBehavior: "submit", onSubmitEditing: () => emailInput.current?.focus(),
                  }} />
                ) : null}
                <LoginField label="Correo electrónico" icon="mail-outline" input={{
                  ref: emailInput, autoComplete: "email", autoCapitalize: "none", autoCorrect: false,
                  keyboardType: "email-address", value: email, onChangeText: update(setEmail),
                  placeholder: "tu@correo.com", returnKeyType: "next", submitBehavior: "submit",
                  onSubmitEditing: () => passwordInput.current?.focus(),
                }} />
                <LoginField label="Contraseña" icon="lock-closed-outline" input={{
                  ref: passwordInput, autoComplete: isRegister ? "new-password" : "password",
                  autoCapitalize: "none", autoCorrect: false, value: password,
                  onChangeText: update(setPassword), secureTextEntry: !passwordVisible,
                  placeholder: "Tu contraseña", returnKeyType: "go", onSubmitEditing: submit,
                }} hint={isRegister ? "Usá al menos 8 caracteres." : undefined}
                accessory={(
                  <Pressable
                    accessibilityLabel={passwordVisible ? "Ocultar contraseña" : "Mostrar contraseña"}
                    accessibilityRole="button"
                    onPress={() => setPasswordVisible((current) => !current)}
                    style={({ pressed }) => [styles.passwordToggle, pressed && styles.pressed]}
                  >
                    <Ionicons aria-hidden accessible={false} name={passwordVisible ? "eye-off-outline" : "eye-outline"}
                      size={20} color={colors.green} />
                  </Pressable>
                )} />
                {isRegister ? (
                  <View style={styles.termsBox}>
                    <Pressable
                      accessibilityRole="checkbox"
                      accessibilityState={{ checked: acceptedTerms }}
                      onPress={() => {
                        setAcceptedTerms((current) => !current);
                        setError(null);
                      }}
                      style={({ pressed }) => [styles.termsToggle, pressed && styles.pressed]}
                    >
                      <View style={[styles.checkbox, acceptedTerms && styles.checkboxChecked]}>
                        {acceptedTerms ? <Ionicons aria-hidden accessible={false} name="checkmark" size={15} color={colors.white} /> : null}
                      </View>
                      <Text style={styles.termsText}>
                        Acepto los términos y condiciones, la política de privacidad y los avisos de seguridad.
                      </Text>
                    </Pressable>
                    <Pressable accessibilityRole="link" onPress={() => router.push("/terminos-condiciones")}
                      style={({ pressed }) => [styles.termsLink, pressed && styles.pressed]}>
                      <Text style={styles.linkText}>Leer términos y condiciones</Text>
                    </Pressable>
                  </View>
                ) : null}
                {error ? (
                  <View accessibilityRole="alert" accessibilityLiveRegion="polite" style={styles.errorBox}>
                    <Ionicons aria-hidden accessible={false} name="alert-circle-outline" size={19} color={colors.danger} />
                    <Text style={styles.error}>{error}</Text>
                  </View>
                ) : null}
                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{ busy: isSubmitting, disabled: isSubmitting }}
                  disabled={isSubmitting}
                  onPress={submit}
                  style={({ pressed }) => [styles.primaryButton, (pressed || isSubmitting) && styles.pressed]}
                >
                  {isSubmitting ? <ActivityIndicator color={colors.white} size="small" /> : null}
                  <Text style={styles.primaryButtonText}>{isSubmitting ? "Un momento…" : buttonLabel}</Text>
                  {!isSubmitting ? <Ionicons aria-hidden accessible={false} name="arrow-forward" size={19} color={colors.white} /> : null}
                </Pressable>
              </View>
              <View style={styles.switchRow}>
                <Text style={styles.switchPrompt}>{isRegister ? "¿Ya tenés cuenta?" : "¿Todavía no tenés cuenta?"}</Text>
                <Pressable
                  accessibilityRole="button"
                  disabled={isSubmitting}
                  onPress={() => {
                    setMode(isRegister ? "login" : "register");
                    setAcceptedTerms(false);
                    setError(null);
                    setPasswordVisible(false);
                  }}
                  style={({ pressed }) => [styles.switchButton, pressed && styles.pressed]}
                >
                  <Text style={styles.linkText}>{isRegister ? "Volver a iniciar sesión" : "Crear una cuenta nueva"}</Text>
                </Pressable>
              </View>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function LoginField({ label, icon, input, hint, accessory }: {
  label: string;
  icon: ComponentProps<typeof Ionicons>["name"];
  input: ComponentPropsWithRef<typeof TextInput>;
  hint?: string;
  accessory?: ReactNode;
}) {
  const [focused, setFocused] = useState(false);
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <View style={[styles.inputBox, focused && styles.inputFocused]}>
        <Ionicons aria-hidden accessible={false} name={icon} size={18} color={focused ? colors.green : colors.muted} />
        <TextInput
          {...input}
          accessibilityLabel={label}
          accessibilityHint={hint}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholderTextColor={colors.muted}
          style={styles.input}
        />
        {accessory}
      </View>
      {hint ? <Text style={styles.hint}>{hint}</Text> : null}
    </View>
  );
}

const contourPath = "M-70 207C-12 146 68 160 93 104S169 12 228 38s67 93 119 84 68-54 131-29";

function LoginBrand({ wide }: { wide: boolean }) {
  return (
    <View style={[styles.brandPanel, wide && styles.brandPanelWide]}>
      <View pointerEvents="none" accessibilityElementsHidden importantForAccessibility="no-hide-descendants"
        aria-hidden style={styles.contours}>
        <Svg width="100%" height="100%" viewBox="0 0 400 330" preserveAspectRatio="xMidYMax slice">
          {Array.from({ length: 11 }, (_, index) => (
            <Path key={index} d={contourPath} transform={`translate(0 ${index * 18})`}
              fill="none" stroke={colors.mint} strokeOpacity={0.19} strokeWidth={1.1} />
          ))}
          <Path d="M14 265C68 234 102 225 120 190S183 154 216 177s77 39 121-14" fill="none"
            stroke={colors.mint} strokeOpacity={0.8} strokeWidth={2} strokeDasharray="4 7" />
          <Circle cx="120" cy="190" r="5" fill={colors.mint} />
          <Circle cx="337" cy="163" r="7" fill={colors.green} stroke={colors.mint} strokeWidth={2} />
        </Svg>
      </View>
      <MiSenderoLogo layout="horizontal" tone="light" markSize={36} wordmarkSize={25} style={styles.brand} />
      {wide ? (
        <View style={styles.brandCopy}>
          <Text style={styles.brandTitle}>Tu próxima salida empieza acá.</Text>
          <Text style={styles.brandText}>Explorá senderos y prepará tu recorrido antes de salir.</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.soft, flex: 1 },
  keyboardArea: { flex: 1 },
  scrollContent: { flexGrow: 1, justifyContent: "center", padding: 16 },
  scrollWide: { padding: 32 },
  container: {
    alignSelf: "center",
    backgroundColor: colors.white,
    borderRadius: 28,
    borderColor: colors.line,
    borderWidth: 1,
    maxWidth: 480,
    overflow: "hidden",
    width: "100%",
  },
  containerWide: { flexDirection: "row", maxWidth: 1000 },
  brandPanel: {
    backgroundColor: colors.green, overflow: "hidden", paddingHorizontal: 22,
    paddingVertical: 16, position: "relative",
  },
  brandPanelWide: {
    flex: 1, gap: 44, minHeight: 520, padding: 36, paddingBottom: 142,
  },
  brand: { alignSelf: "flex-start" },
  brandCopy: { gap: 14 },
  brandTitle: {
    color: colors.white, fontFamily: typography.extraBold, fontSize: 49,
    letterSpacing: -1.7, lineHeight: 49,
  },
  brandText: { color: colors.mint, fontFamily: typography.regular, fontSize: 17, lineHeight: 25, maxWidth: 275 },
  contours: { ...StyleSheet.absoluteFill, left: "22%", top: "35%" },
  formPanel: { justifyContent: "center", padding: 22, gap: 23 },
  formPanelWide: { flex: 1.15, minWidth: 0, padding: 42 },
  heading: { gap: 7 },
  title: {
    color: colors.ink, fontFamily: typography.extraBold, fontSize: 35, letterSpacing: -1.1, lineHeight: 39,
  },
  subtitle: { color: colors.muted, fontFamily: typography.regular, fontSize: 15, lineHeight: 22 },
  form: { gap: 16 },
  field: { gap: 6 },
  label: { color: colors.ink, fontFamily: typography.bold, fontSize: 14, lineHeight: 19 },
  hint: { color: colors.muted, fontFamily: typography.regular, fontSize: 13, lineHeight: 18 },
  inputBox: {
    alignItems: "center", backgroundColor: colors.page, borderColor: colors.line, borderRadius: 13,
    borderWidth: 2, flexDirection: "row", gap: 9, minHeight: 52, paddingLeft: 12,
  },
  inputFocused: { backgroundColor: colors.white, borderColor: colors.green },
  input: {
    color: colors.ink, flex: 1, fontFamily: typography.regular, fontSize: 16, minWidth: 0,
    paddingRight: 10, paddingVertical: 12,
    ...(Platform.OS === "web" ? { outlineWidth: 0 } : {}),
  },
  passwordToggle: { alignItems: "center", justifyContent: "center", minHeight: 44, width: 44 },
  errorBox: {
    alignItems: "flex-start", backgroundColor: "#FFF4F2", borderColor: "#F2B8B2", borderRadius: 12,
    borderWidth: 1, flexDirection: "row", gap: 9, padding: 11,
  },
  error: { color: colors.danger, flex: 1, fontFamily: typography.medium, fontSize: 14, lineHeight: 20 },
  termsBox: { backgroundColor: colors.page, borderRadius: 12, paddingHorizontal: 12 },
  termsToggle: { alignItems: "flex-start", flexDirection: "row", gap: 10, minHeight: 44, paddingTop: 11 },
  checkbox: {
    alignItems: "center", backgroundColor: colors.white, borderColor: colors.green, borderRadius: 6,
    borderWidth: 2, height: 22, justifyContent: "center", width: 22,
  },
  checkboxChecked: { backgroundColor: colors.green },
  termsText: { color: colors.muted, flex: 1, fontFamily: typography.regular, fontSize: 13, lineHeight: 19 },
  termsLink: { alignSelf: "flex-start", justifyContent: "center", marginLeft: 32, minHeight: 44 },
  linkText: { color: colors.green, fontFamily: typography.bold, fontSize: 14, lineHeight: 20, textDecorationLine: "underline" },
  primaryButton: {
    alignItems: "center", backgroundColor: colors.green, borderRadius: 13, flexDirection: "row",
    gap: 10, justifyContent: "center", minHeight: 52, padding: 12,
  },
  pressed: { opacity: 0.78 },
  primaryButtonText: { color: colors.white, fontFamily: typography.bold, fontSize: 16, lineHeight: 22 },
  switchRow: {
    alignItems: "center", borderTopColor: colors.line, borderTopWidth: 1, flexDirection: "row",
    flexWrap: "wrap", columnGap: 8, justifyContent: "center", paddingTop: 7,
  },
  switchPrompt: { color: colors.muted, fontFamily: typography.regular, fontSize: 14, lineHeight: 20 },
  switchButton: { justifyContent: "center", minHeight: 44 },
});
