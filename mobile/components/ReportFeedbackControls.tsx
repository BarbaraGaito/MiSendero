import { useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import type { ReportFeedbackValue, TrailReport } from "../../types";
import { enqueue, runSync } from "../../services/syncQueue";
import { userMessage } from "../../services/userMessages";
import { reportAge, reportCommunityLabel } from "../../services/reportExperience";
import { colors } from "./MiSenderoUI";

const answers: { value: ReportFeedbackValue; label: string }[] = [
  { value: "still_there", label: "Sigue igual" },
  { value: "not_there", label: "Ya no está" },
  { value: "unsure", label: "No pude verificar" },
];

export function ReportFeedbackControls({ report, onChanged, onRecorded, observedAt }: {
  report: TrailReport; onChanged?: () => Promise<void>; onRecorded?: () => void; observedAt?: string;
}) {
  const [answer, setAnswer] = useState(report.my_feedback ?? null);
  const [busy, setBusy] = useState(false);
  const [recordedAnswer, setRecordedAnswer] = useState<ReportFeedbackValue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busyRef = useRef(false);
  const recordedAnswerRef = useRef<ReportFeedbackValue | null>(null);
  useEffect(() => { recordedAnswerRef.current = null; setRecordedAnswer(null); }, [report.id]);
  useEffect(() => { setAnswer(report.my_feedback ?? null); }, [report.id, report.my_feedback]);
  const record = async (feedback: ReportFeedbackValue) => {
    if (busyRef.current || recordedAnswerRef.current === feedback) return;
    busyRef.current = true; setBusy(true); setError(null);
    try {
      await enqueue("report_feedback", { reportId: report.id, trailId: report.trail_id, feedback, observed_at: observedAt ?? new Date().toISOString() });
      recordedAnswerRef.current = feedback;
      setRecordedAnswer(feedback);
      setAnswer(feedback);
      onRecorded?.();
      void runSync().then(() => onChanged?.()).catch(() => undefined);
    } catch (cause) {
      setError(userMessage(cause, "No pudimos guardar tu respuesta. Intentá nuevamente."));
    } finally { busyRef.current = false; setBusy(false); }
  };
  return <View style={styles.container}>
    <Text style={styles.meta}>Observado {reportAge(report.observed_at || report.created_at)}</Text>
    <Text style={styles.meta}>{reportCommunityLabel(report)}</Text>
    {report.expires_at && report.community_status !== "resolved" ? <Text style={styles.meta}>Vigente hasta {new Date(report.expires_at).toLocaleDateString("es-AR")}, salvo nuevas observaciones.</Text> : null}
    <View style={styles.options}>
      {answers.map(item => <Pressable key={item.value} accessibilityRole="button" accessibilityState={{ selected: answer === item.value, disabled: busy || recordedAnswer === item.value }}
        disabled={busy || recordedAnswer === item.value} onPress={() => { void record(item.value); }}
        style={[styles.button, answer === item.value && styles.selected, busy && styles.busy]}>
        <Text style={[styles.label, answer === item.value && styles.selectedLabel]}>{item.label}</Text>
      </Pressable>)}
    </View>
    {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
  </View>;
}

const styles = StyleSheet.create({
  container: { gap: 7 }, meta: { color: colors.muted, fontSize: 12, lineHeight: 17 },
  options: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  button: { minHeight: 44, borderRadius: 13, backgroundColor: colors.soft, paddingHorizontal: 10, justifyContent: "center" },
  selected: { backgroundColor: colors.green },
  label: { color: colors.greenDark, fontSize: 12, fontWeight: "800" },
  selectedLabel: { color: colors.white }, busy: { opacity: 0.6 }, error: { color: colors.danger, fontSize: 12 },
});
