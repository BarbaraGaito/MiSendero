import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { initDB } from "../../database/database";
import {
  getTrailRatingSummary,
  getTrailReviews,
  TrailRatingSummary,
  TrailReview,
} from "../../database/sessionsRepository";
import { getTrailById } from "../../services/trailRepository";
import { Trail } from "../../types";
import { InfoCard, ScreenShell, TopBar, colors } from "../components/MiSenderoUI";

export default function TrailReviewsScreen() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const trailId = Number(id);
  const [trail, setTrail] = useState<Trail | null>(null);
  const [summary, setSummary] = useState<TrailRatingSummary | null>(null);
  const [reviews, setReviews] = useState<TrailReview[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    const loadReviews = async () => {
      if (!trailId) {
        setError("No encontramos el sendero seleccionado.");
        setIsLoading(false);
        return;
      }

      try {
        await initDB();
        const [trailData, ratingSummary, trailReviews] = await Promise.all([
          getTrailById(trailId).catch(() => null),
          getTrailRatingSummary(trailId),
          getTrailReviews(trailId),
        ]);

        if (!isMounted) return;

        setTrail(trailData);
        setSummary(ratingSummary);
        setReviews(trailReviews);
        setError(null);
      } catch {
        if (!isMounted) return;
        setError("No pudimos cargar las opiniones de este sendero.");
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    loadReviews();

    return () => {
      isMounted = false;
    };
  }, [trailId]);

  return (
    <ScreenShell>
      <TopBar title="Opiniones" onBack={() => router.back()} />

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>{trail?.name || "Sendero"}</Text>
        <Text style={styles.location}>{trail?.location || "Opiniones reales de la app"}</Text>

        {isLoading ? <Text style={styles.statusText}>Cargando opiniones...</Text> : null}
        {error ? <Text style={styles.statusText}>{error}</Text> : null}

        {!isLoading && !error ? (
          <>
            <InfoCard style={styles.summaryCard}>
              {summary ? (
                <>
                  <View style={styles.summaryHeader}>
                    <Text style={styles.averageText}>{summary.averageRating.toFixed(1)}</Text>
                    <View style={styles.summaryStars}>
                      <Stars rating={summary.averageRating} />
                      <Text style={styles.summaryCount}>
                        {summary.reviewCount} opinion{summary.reviewCount === 1 ? "" : "es"}
                      </Text>
                    </View>
                  </View>
                </>
              ) : (
                <>
                  <Text style={styles.cardTitle}>Todavia no hay opiniones</Text>
                  <Text style={styles.cardText}>
                    Cuando alguien termine este sendero y deje su calificacion,
                    va a aparecer aca.
                  </Text>
                </>
              )}
            </InfoCard>

            {reviews.map((review) => (
              <InfoCard key={review.id} style={styles.reviewCard}>
                <View style={styles.reviewHeader}>
                  <Stars rating={review.rating} />
                  <Text style={styles.reviewDate}>{formatDate(review.reviewedAt)}</Text>
                </View>
                <Text style={styles.reviewText}>
                  {review.reviewText || "Sin comentario escrito."}
                </Text>
              </InfoCard>
            ))}
          </>
        ) : null}
      </ScrollView>
    </ScreenShell>
  );
}

function Stars({ rating }: { rating: number }) {
  return (
    <View style={styles.starsRow}>
      {[1, 2, 3, 4, 5].map((value) => (
        <Ionicons
          key={value}
          name={value <= Math.round(rating) ? "star" : "star-outline"}
          size={18}
          color={colors.primary}
        />
      ))}
    </View>
  );
}

function formatDate(timestamp: number) {
  return new Intl.DateTimeFormat("es-AR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(timestamp));
}

const styles = StyleSheet.create({
  scroll: {
    paddingBottom: 110,
  },
  title: {
    color: colors.ink,
    fontSize: 28,
    fontWeight: "900",
    lineHeight: 34,
  },
  location: {
    color: colors.muted,
    fontSize: 15,
    marginTop: 6,
    marginBottom: 18,
  },
  statusText: {
    color: colors.muted,
    fontSize: 14,
    fontWeight: "800",
    marginBottom: 14,
  },
  summaryCard: {
    marginBottom: 14,
  },
  summaryHeader: {
    alignItems: "center",
    flexDirection: "row",
    gap: 14,
  },
  averageText: {
    color: colors.ink,
    fontSize: 42,
    fontWeight: "900",
    lineHeight: 46,
  },
  summaryStars: {
    flex: 1,
    gap: 5,
  },
  summaryCount: {
    color: colors.muted,
    fontSize: 13,
    fontWeight: "800",
  },
  reviewCard: {
    marginBottom: 12,
  },
  reviewHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 10,
  },
  reviewDate: {
    color: colors.muted,
    flexShrink: 0,
    fontSize: 12,
    fontWeight: "800",
  },
  reviewText: {
    color: colors.ink,
    fontSize: 14,
    lineHeight: 21,
    marginTop: 10,
  },
  starsRow: {
    flexDirection: "row",
    gap: 2,
  },
  cardTitle: {
    color: colors.ink,
    fontSize: 17,
    fontWeight: "900",
  },
  cardText: {
    color: colors.muted,
    fontSize: 14,
    lineHeight: 21,
    marginTop: 6,
  },
});
