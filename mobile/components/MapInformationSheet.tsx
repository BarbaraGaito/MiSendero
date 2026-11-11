import type { ReactNode } from "react";
import { Ionicons } from "@expo/vector-icons";
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, typography } from "./MiSenderoUI";

type MapInformationSheetProps = {
  visible: boolean;
  attribution: string;
  onClose: () => void;
  onOpenAttributions?: () => void;
  children?: ReactNode;
};

export function MapInformationSheet({ visible, attribution, onClose, onOpenAttributions, children }: MapInformationSheetProps) {
  if (!visible) return null;
  return <Modal transparent visible animationType="fade" onRequestClose={onClose}>
    <View style={styles.backdrop}>
      <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessible={false} />
      <SafeAreaView edges={["bottom"]} style={styles.sheet} accessibilityViewIsModal>
        <View style={styles.header}>
          <Text accessibilityRole="header" style={styles.title}>Información del mapa</Text>
          <Pressable accessibilityRole="button" accessibilityLabel="Cerrar información del mapa"
            onPress={onClose} style={styles.close}>
            <Ionicons name="close" size={24} color={colors.ink} />
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          {children}
          <View style={styles.credits}>
            <Text accessibilityRole="header" style={styles.sectionTitle}>Fuentes y copyright</Text>
            <Text style={styles.body}>{attribution}</Text>
            {onOpenAttributions && <Pressable accessibilityRole="button" onPress={onOpenAttributions}
              style={styles.licenseButton}>
              <Text style={styles.licenseText}>Ver todas las fuentes y licencias</Text>
              <Ionicons name="chevron-forward" size={18} color={colors.greenDark} />
            </Pressable>}
          </View>
        </ScrollView>
      </SafeAreaView>
    </View>
  </Modal>;
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(20,36,28,0.38)" },
  sheet: { maxHeight: "80%", backgroundColor: colors.white, borderTopLeftRadius: 24, borderTopRightRadius: 24 },
  header: { flexDirection: "row", alignItems: "center", paddingLeft: 24, paddingRight: 12, paddingTop: 16, paddingBottom: 8 },
  title: { flex: 1, fontFamily: typography.extraBold, fontSize: 21, color: colors.ink },
  close: { width: 44, height: 44, alignItems: "center", justifyContent: "center", borderRadius: 22 },
  content: { paddingHorizontal: 24, paddingBottom: 24, gap: 20 },
  credits: { gap: 8 },
  sectionTitle: { fontFamily: typography.bold, color: colors.ink, fontSize: 15 },
  body: { color: colors.muted, fontSize: 13, lineHeight: 20 },
  licenseButton: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8,
    minHeight: 44, paddingVertical: 10 },
  licenseText: { flex: 1, color: colors.greenDark, fontFamily: typography.bold, fontSize: 14 },
});
