import { ScrollView, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import {
  Card,
  PrimaryButton,
  ScreenShell,
  TopBar,
  colors,
} from "../components/MiSenderoUI";
import { CURRENT_TERMS_VERSION } from "../../services/legalConsent";

import { sections } from "../../backend/src/terms.json";

export default function TermsScreen() {
  return (
    <ScreenShell>
      <TopBar
        title="Terminos y seguridad"
        subtitle={`Version ${CURRENT_TERMS_VERSION}`}
        onBack={() => router.back()}
      />

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <Card tone="red">
          <Text style={styles.warningTitle}>Aviso importante</Text>
          <Text style={styles.warningText}>
            MiSendero es una herramienta de apoyo para senderismo. No garantiza
            deteccion de emergencias, anomalias cardiacas ni riesgos del
            terreno.
          </Text>
        </Card>

        {sections.map((section) => (
          <Card key={section.title}>
            <Text style={styles.sectionTitle}>{section.title}</Text>
            <Text style={styles.sectionBody}>{section.body}</Text>
          </Card>
        ))}

        <Card tone="green">
          <Text style={styles.sectionTitle}>Consentimiento</Text>
          <Text style={styles.sectionBody}>
            Al crear una cuenta, el usuario declara que leyo y acepta estos
            términos de uso. El tratamiento fisiológico y la analítica requieren
            decisiones independientes en Perfil; los permisos del sistema se administran por separado.
          </Text>
        </Card>

        <View style={styles.footer}>
          <PrimaryButton label="Entendido" onPress={() => router.back()} />
        </View>
      </ScrollView>
    </ScreenShell>
  );
}

const styles = StyleSheet.create({
  scrollContent: {
    paddingBottom: 28,
  },
  warningTitle: {
    color: colors.ink,
    fontSize: 18,
    fontWeight: "900",
    marginBottom: 8,
  },
  warningText: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: "700",
    lineHeight: 21,
  },
  sectionTitle: {
    color: colors.ink,
    fontSize: 16,
    fontWeight: "900",
    marginBottom: 8,
  },
  sectionBody: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "600",
    lineHeight: 21,
  },
  footer: {
    marginTop: 2,
  },
});
