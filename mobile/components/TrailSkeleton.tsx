import { useEffect, useRef } from "react";
import { Animated, StyleSheet, View } from "react-native";
import { colors } from "./MiSenderoUI";

type TrailSkeletonProps = {
  variant: "detail" | "list";
  count?: number;
};

export function TrailSkeleton({ variant, count = 2 }: TrailSkeletonProps) {
  const opacity = useRef(new Animated.Value(0.55)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 1, duration: 800, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0.55, duration: 800, useNativeDriver: true }),
      ])
    );
    animation.start();
    return () => animation.stop();
  }, [opacity]);

  const block = (style: object) => <Animated.View style={[styles.block, style, { opacity }]} />;

  return (
    <View
      accessibilityLabel={variant === "detail" ? "Cargando sendero" : "Cargando senderos"}
      accessibilityLiveRegion="polite"
      accessibilityRole="progressbar"
      testID={`trail-skeleton-${variant}`}
    >
      {variant === "detail" ? (
        <>
          {block(styles.cover)}
          {block(styles.detailTitle)}
          {block(styles.detailLocation)}
          <View style={styles.metrics}>
            {[0, 1, 2, 3].map((item) => (
              <View key={item} style={styles.metric}>
                {block(styles.metricLabel)}
                {block(styles.metricValue)}
              </View>
            ))}
          </View>
          {block(styles.detailAction)}
          {block(styles.detailSection)}
        </>
      ) : (
        Array.from({ length: count }, (_, item) => (
          <View key={item} style={styles.card}>
            {block(styles.cardImage)}
            <View style={styles.cardBody}>
              {block(styles.cardTitle)}
              {block(styles.cardLocation)}
              {block(styles.cardMeta)}
            </View>
          </View>
        ))
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  block: { backgroundColor: colors.line, borderRadius: 10 },
  cover: { height: 230, borderRadius: 28, marginBottom: 22 },
  detailTitle: { height: 30, width: "78%", marginBottom: 12 },
  detailLocation: { height: 16, width: "52%", marginBottom: 20 },
  metrics: { flexDirection: "row", flexWrap: "wrap", gap: 12, marginBottom: 16 },
  metric: {
    width: "48%",
    flexGrow: 1,
    backgroundColor: colors.white,
    borderColor: colors.line,
    borderRadius: 18,
    borderWidth: 1,
    padding: 16,
  },
  metricLabel: { height: 13, width: "65%", marginBottom: 12 },
  metricValue: { height: 20, width: "45%" },
  detailAction: { height: 52, borderRadius: 16, marginBottom: 16 },
  detailSection: { height: 100, borderRadius: 20 },
  card: {
    backgroundColor: colors.white,
    borderColor: colors.line,
    borderRadius: 22,
    borderWidth: 1,
    marginBottom: 14,
    overflow: "hidden",
  },
  cardImage: { height: 126, borderRadius: 0 },
  cardBody: { padding: 16 },
  cardTitle: { height: 20, width: "72%", marginBottom: 10 },
  cardLocation: { height: 14, width: "55%", marginBottom: 12 },
  cardMeta: { height: 14, width: "44%" },
});
