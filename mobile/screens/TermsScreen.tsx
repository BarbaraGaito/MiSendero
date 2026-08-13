import React from "react";
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

const sections = [
  {
    title: "Uso informativo, no medico",
    body:
      "MiSendero no es un servicio medico, no reemplaza una consulta profesional y no debe usarse para diagnosticar, tratar, prevenir o confirmar enfermedades, lesiones o emergencias de salud.",
  },
  {
    title: "Anomalias cardiacas y alertas",
    body:
      "Si MiSendero no detecta una anomalia cardiaca, una arritmia, agotamiento, hipoxia, deshidratacion u otra condicion, eso no significa que el usuario este fuera de riesgo. La ausencia de alertas no garantiza seguridad fisica ni buen estado de salud.",
  },
  {
    title: "Sensores y falsos resultados",
    body:
      "Las mediciones de frecuencia cardiaca, actividad fisica, ubicacion, altitud y movimiento pueden ser imprecisas, demorarse o fallar por bateria, conectividad, permisos, cobertura GPS, uso incorrecto del dispositivo o limitaciones del sensor. La app puede generar falsos positivos o falsos negativos.",
  },
  {
    title: "IA y recomendaciones",
    body:
      "Las funciones de IA funcionan como estimaciones de apoyo basadas en datos disponibles y modelos entrenados. Sus resultados son orientativos, pueden equivocarse y no sustituyen criterio personal, planificacion, supervision profesional ni protocolos de seguridad.",
  },
  {
    title: "Emergencias",
    body:
      "Ante dolor de pecho, falta de aire, mareos intensos, perdida de conciencia, desorientacion, lesion, condiciones climaticas peligrosas o cualquier sospecha de emergencia, el usuario debe detener la actividad y contactar a emergencias, rescate local o asistencia medica.",
  },
  {
    title: "Mapas, GPS y uso sin conexion",
    body:
      "Los mapas offline, rutas, perspectiva del terreno y posicion GPS son herramientas de apoyo. Pueden estar desactualizados o no coincidir con el terreno real. El usuario debe llevar bateria suficiente, agua, abrigo, medios alternativos de orientacion y avisar su itinerario.",
  },
  {
    title: "Datos sensibles y privacidad",
    body:
      "Los datos fisiologicos y de actividad fisica son sensibles. Se almacenan localmente cuando corresponde, requieren consentimiento explicito para su uso y, si se usan con fines analiticos o de entrenamiento, se procesan mediante limpieza y anonimizacion, eliminando identificadores personales y ubicaciones exactas.",
  },
  {
    title: "Responsabilidad del usuario",
    body:
      "El usuario acepta no depender exclusivamente de MiSendero para seguridad, salud, navegacion o rescate. Debe evaluar sus condiciones fisicas, dificultad del recorrido, clima, equipamiento y restricciones locales antes y durante cada salida.",
  },
];

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
            terminos, incluyendo los limites de responsabilidad, privacidad,
            tratamiento de datos sensibles y uso informativo de la IA.
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
