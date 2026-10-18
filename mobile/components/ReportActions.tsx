import { useState } from "react";
import { Alert, Modal, Text, TextInput, View } from "react-native";
import { getAuthSession } from "../../services/authSession";
import { flagReport, blockReportAuthor, withdrawReport, correctReport } from "../../services/api";
import { userMessage } from "../../services/userMessages";
import { db } from "../../database/connection";
import { TrailReport } from "../../types";
import { PrimaryButton, Card } from "./MiSenderoUI";

export function ReportActions({ report, onChanged }: { report: TrailReport; onChanged: () => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [summary, setSummary] = useState(report.issue_summary);
  const [details, setDetails] = useState(report.details || "");
  const [busy, setBusy] = useState(false);
  const perform = async (action: "flag" | "block" | "withdraw" | "correct") => {
    setBusy(true);
    try {
      const session = await getAuthSession();
      if (!session) throw new Error("Iniciá sesión para gestionar reportes.");
      let removed: number[] = [];
      if (action === "flag") await flagReport(report.id, "Contenido inapropiado, abusivo o datos personales", session.token);
      if (action === "block") removed = (await blockReportAuthor(report.id, session.token)).hidden_report_ids;
      if (action === "withdraw") { await withdrawReport(report.id, session.token); removed = [report.id]; }
      if (action === "correct") { await correctReport(report.id, summary, details, session.token); setEditing(false); }
      // Immediately purge affected public copies on this installation as well.
      if (removed.length) {
        const maps = await db.getAllAsync<{ id: number; reports_json: string }>("SELECT id, reports_json FROM offline_maps WHERE user_id = ? AND reports_json IS NOT NULL", [session.user.id]);
        for (const map of maps) {
          const reports = JSON.parse(map.reports_json) as TrailReport[];
          await db.runAsync("UPDATE offline_maps SET reports_json = ? WHERE id = ?", [JSON.stringify(reports.filter((item) => !removed.includes(item.id))), map.id]);
        }
      }
      await onChanged();
      if (action === "flag") Alert.alert("Denuncia recibida", "El reporte queda disponible para revisión por moderación. La denuncia no confirma su retiro.");
    } catch (error) { Alert.alert("No se pudo completar", userMessage(error, "Reintentá con conexión.")); }
    finally { setBusy(false); }
  };
  const open = () => Alert.alert("Gestionar reporte", "Podés denunciar contenido o dejar de ver reportes de su autor. Los cambios remotos requieren conexión.", [
    { text: "Cancelar", style: "cancel" },
    ...(report.is_mine ? [
      { text: "Corregir mi reporte", onPress: () => setEditing(true) },
      { text: "Retirar mi reporte", style: "destructive" as const, onPress: () => { void perform("withdraw"); } },
    ] : [
      { text: "Denunciar contenido", onPress: () => { void perform("flag"); } },
      { text: "Bloquear autor", style: "destructive" as const, onPress: () => { void perform("block"); } },
    ]),
  ]);
  return <>
    <PrimaryButton label="Opciones del reporte" tone="secondary" onPress={open} isLoading={busy} />
    <Modal visible={editing} transparent onRequestClose={() => setEditing(false)}>
      <View style={{ flex: 1, justifyContent: "center", padding: 20, backgroundColor: "rgba(0,0,0,0.5)" }}>
        <Card>
          <Text>Corregir mi reporte</Text>
          <TextInput accessibilityLabel="Resumen del reporte" value={summary} maxLength={300} onChangeText={setSummary} />
          <TextInput accessibilityLabel="Detalles del reporte" value={details} maxLength={1000} onChangeText={setDetails} multiline />
          <PrimaryButton label="Guardar corrección" disabled={!summary.trim()} isLoading={busy} onPress={() => { void perform("correct"); }} />
          <PrimaryButton label="Cancelar" tone="secondary" onPress={() => setEditing(false)} />
        </Card>
      </View>
    </Modal>
  </>;
}
