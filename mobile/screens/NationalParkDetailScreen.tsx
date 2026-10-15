import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { ReactNode, useCallback, useEffect, useState } from "react";
import { Alert, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { formatKilometers } from "../../services/geoUtils";
import { getNationalPark, getParkRegistration, getRegistrationLabel, ParkResult, parkProfileNeedsReview } from "../../services/nationalParks";
import { NationalPark } from "../../types";
import { colors, PrimaryButton, ScreenShell, StatusNotice as SharedStatusNotice, TopBar } from "../components/MiSenderoUI";
import { OfficialLink, openOfficialUrl } from "../components/NationalParkUI";

export default function NationalParkDetailScreen() {
  const { slug, trailId } = useLocalSearchParams<{ slug?: string; trailId?: string }>();
  const [result, setResult] = useState<ParkResult<NationalPark> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setResult(null); setLoading(true); setError(null);
    if (!slug) { setError("Parque no indicado."); setLoading(false); return; }
    try { setResult(await getNationalPark(slug)); }
    catch (e) { setError(e instanceof Error ? e.message : "Ficha no disponible."); }
    finally { setLoading(false); }
  }, [slug]);
  useEffect(() => { void load(); }, [load]);
  const park = result?.data;
  const selectedTrail = park?.trails.find((trail) => String(trail.id) === trailId);
  const registration = park ? getParkRegistration(park, selectedTrail?.name) : null;
  return <ScreenShell>
    <TopBar title="Informacion del parque" onBack={() => router.back()} />
    <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      {loading && <SharedStatusNotice title="Consultando parque" message="Cargando ficha institucional." isLoading />}
      {error && <SharedStatusNotice title="No se pudo consultar" message={error} tone="error" actionLabel="Reintentar" onAction={load} />}
      {park && <>
        <Text style={styles.title}>{park.name}</Text>
        <Text style={styles.muted}>{park.provinces.join(" / ")}</Text>
        <Text style={styles.scope}>{selectedTrail?.name || park.scope}</Text>
        <View style={styles.reviewRow}>
          <Text style={[styles.muted, styles.flex]}>Fuentes revisadas: {formatDate(park.checked_at)}</Text>
          <Pressable accessibilityRole="button" accessibilityLabel="Actualizar ficha" onPress={load} style={styles.iconButton}>
            <Ionicons name="refresh-outline" size={22} color={colors.greenDark} />
          </Pressable>
        </View>
        {result.fromCache && <SharedStatusNotice title="Informacion guardada"
          message="Conectate para consultar los avisos actuales del parque y completar el registro." tone="warning" />}
        {parkProfileNeedsReview(park) && <SharedStatusNotice title="Reconfirmar requisitos"
          message="Consulta los requisitos vigentes en la pagina oficial del parque antes de salir." tone="warning" />}
        <Section title="Alertas y cierres oficiales" icon="warning-outline">
          <OfficialLink label="Entrar a la pagina oficial del parque" url={park.notices_url} />
          <Text style={styles.trailName}>Servicio Meteorologico Nacional</Text>
          <Text style={styles.body}>{park.weather_area}</Text>
          <OfficialLink label="Consultar alertas en el SMN" url={park.live_status.weather_url} />
        </Section>
        {registration && <Section title="Registro de trekking" icon="clipboard-outline">
          <Text style={styles.status}>{getRegistrationLabel(park, new Date(), selectedTrail?.name)}</Text>
          <Text style={styles.body}>{registration.summary}</Text>
          <PrimaryButton label={registration.form_url ? "Abrir registro oficial" :
            registration.mode === "in_person" ? "Consultar registro presencial" : "Consultar requisitos oficiales"}
            icon="open-outline" onPress={() => void openOfficialUrl(registration.form_url || registration.source_url)} />
          {registration.form_url && <Text style={styles.muted}>Conserva el comprobante del registro emitido por el parque.</Text>}
          <OfficialLink label="Condiciones del registro" url={registration.source_url} />
        </Section>}
        <Section title="Acceso y condiciones" icon="trail-sign-outline">
          <Text style={styles.body}>{park.access.text}</Text>
          <OfficialLink label="Consultar acceso oficial" url={park.access.source_url} />
        </Section>
        <Section title="Normas del parque" icon="shield-checkmark-outline">
          {park.rules.items.map((item) => <Text key={item} style={styles.body}>{item}</Text>)}
          <OfficialLink label="Normativas y recomendaciones" url={park.rules.source_url} />
        </Section>
        <Section title="Pernocte y acampe" icon="moon-outline">
          <Text style={styles.body}>{park.overnight.text}</Text>
          <OfficialLink label="Areas y requisitos de pernocte" url={park.overnight.source_url} />
          {park.overnight.booking_url && <OfficialLink label={park.slug === "quebrada-del-condorito" ? "Formulario de pernocte" : "Reservas del operador autorizado"} url={park.overnight.booking_url} />}
        </Section>
        <Section title="Fuego" icon="flame-outline">
          <Text style={styles.body}>{park.fire.text}</Text>
          <OfficialLink label="Restricciones oficiales de fuego" url={park.fire.source_url} />
        </Section>
        <Section title="Contacto institucional" icon="call-outline">
          <Text style={styles.body}>{park.contact.name}</Text>
          {park.contact.phone && <ContactLink label={park.contact.phone} url={`tel:${park.contact.phone}`} />}
          <ContactLink label={park.contact.email} url={`mailto:${park.contact.email}`} />
          <OfficialLink label="Datos oficiales de contacto" url={park.contact.source_url} />
        </Section>
        <Section title="Senderos del catalogo" icon="walk-outline">
          {park.trails.map((trail) => <Pressable key={trail.id} accessibilityRole="button" accessibilityLabel={`Ver ${trail.name}`}
            style={styles.trailRow} onPress={() => router.push({ pathname: "/trail-detail", params: { id: String(trail.id) } })}>
            <View style={styles.flex}>
              <Text style={styles.trailName}>{trail.name}</Text>
              <Text style={styles.muted}>{trail.distance_km == null ? "Distancia a confirmar" : formatKilometers(Number(trail.distance_km))} - {trail.duration || "Duracion a confirmar"}</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.greenDark} />
          </Pressable>)}
        </Section>
        <OfficialLink label="Sitio institucional del parque" url={park.website_url} />
      </>}
    </ScrollView>
  </ScreenShell>;
}

function Section({ title, icon, children }: { title: string; icon: keyof typeof Ionicons.glyphMap; children: ReactNode }) {
  return <View style={styles.section}>
    <View style={styles.heading}><Ionicons name={icon} size={23} color={colors.greenDark} /><Text style={styles.headingText}>{title}</Text></View>
    {children}
  </View>;
}

function ContactLink({ label, url }: { label: string; url: string }) {
  return <Pressable accessibilityRole="link" style={styles.trailRow} onPress={() => {
    void Linking.openURL(url).catch(() => Alert.alert("Contacto", `No se pudo abrir. Contacto: ${label}`));
  }}><Text style={styles.contact}>{label}</Text></Pressable>;
}

function formatDate(date: string) {
  const parsed = new Date(`${date}T12:00:00-03:00`);
  return Number.isFinite(parsed.getTime()) ? parsed.toLocaleDateString("es-AR") : "sin fecha";
}

const styles = StyleSheet.create({
  content: { paddingBottom: 40, width: "100%", maxWidth: 720, alignSelf: "center" },
  title: { color: colors.ink, fontSize: 26, fontWeight: "800", lineHeight: 33, marginBottom: 8 },
  scope: { color: colors.ink, fontSize: 14, lineHeight: 21, marginTop: 14 },
  muted: { color: colors.muted, fontSize: 13, lineHeight: 20 },
  reviewRow: { flexDirection: "row", alignItems: "center", gap: 8, marginVertical: 12 },
  iconButton: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  section: { paddingVertical: 22, borderTopWidth: 1, borderColor: colors.line, gap: 12 },
  heading: { flexDirection: "row", alignItems: "center", gap: 10 },
  headingText: { color: colors.ink, fontSize: 18, lineHeight: 25, fontWeight: "800", flex: 1 },
  status: { color: colors.orange, fontSize: 14, fontWeight: "700", lineHeight: 21 },
  body: { color: colors.ink, fontSize: 14, lineHeight: 22 },
  trailRow: { flexDirection: "row", gap: 10, alignItems: "center", paddingVertical: 12, minHeight: 44 },
  trailName: { color: colors.greenDark, fontSize: 15, lineHeight: 22, fontWeight: "700", marginBottom: 4 },
  contact: { color: colors.greenDark, fontSize: 14, lineHeight: 21, flexShrink: 1 },
  flex: { flex: 1, minWidth: 0 },
});
