import { StyleSheet, Text, View } from "react-native";

interface Props {
  title: string;
  value: string | number;
}

export default function StatsCard({ title, value }: Props) {
  return (
    <View style={styles.card}>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    backgroundColor: "#121A16",
    borderWidth: 1,
    borderColor: "#223128",
    padding: 16,
    borderRadius: 20,
  },
  title: { color: "#8FA395", fontSize: 13, marginBottom: 4 },
  value: { color: "#F6FFF8", fontSize: 22, fontWeight: "800" },
});
