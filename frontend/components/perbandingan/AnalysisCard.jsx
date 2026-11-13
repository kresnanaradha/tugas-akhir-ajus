// perbandingan AI dua rapat: kesamaan, perbedaan, perkembangan, dan kesimpulan
import { Feather } from "@expo/vector-icons";
import { useEffect, useState } from "react";
import { ActivityIndicator, Text, View } from "react-native";
import { SectionCard } from "@/components/perbandingan/SectionCard";
import { styles } from "@/components/perbandingan/styles";
import { colors, spacing } from "@/constants/theme";
import { getComparisonAnalysis } from "@/lib/api";

const ANALYSIS_BLOCKS = [
  ["similarities", "Kesamaan", "link", colors.success],
  ["differences", "Perbedaan", "shuffle", colors.info],
  ["progress", "Perkembangan dari Rapat A ke B", "trending-up", colors.goldDeep],
];

export function AnalysisCard({ leftId, rightId }) {
  const [state, setState] = useState({ status: "loading", data: null, error: "" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", data: null, error: "" });
    getComparisonAnalysis(leftId, rightId)
      .then((data) => !cancelled && setState({ status: "done", data, error: "" }))
      .catch((e) => !cancelled && setState({ status: "error", data: null, error: e.message || "" }));
    return () => {
      cancelled = true;
    };
  }, [leftId, rightId]);

  const data = state.data;
  return (
    <SectionCard icon="cpu" title="Perbandingan AI">
      {state.status === "loading" && (
        <View style={styles.aiLoading}>
          <ActivityIndicator color={colors.gold} />
          <Text style={styles.mutedText}>AI sedang membandingkan kedua rapat...</Text>
        </View>
      )}
      {state.status === "error" && <Text style={styles.stateText}>{state.error || "Perbandingan AI gagal dibuat."}</Text>}
      {data && (
        <>
          {!!(data.about_a || data.about_b) && (
            <View style={{ gap: spacing.xs }}>
              {!!data.about_a && <Text style={styles.bodyText}>{data.about_a}</Text>}
              {!!data.about_b && <Text style={styles.bodyText}>{data.about_b}</Text>}
            </View>
          )}
          {ANALYSIS_BLOCKS.map(([key, title, icon, color]) =>
            data[key]?.length ? (
              <View key={key} style={{ gap: spacing.xs }}>
                <Text style={styles.aiHeading}>{title}</Text>
                {data[key].map((line, i) => (
                  <View key={i} style={styles.bulletRow}>
                    <Feather name={icon} size={13} color={color} style={{ marginTop: 3 }} />
                    <Text style={[styles.bodyText, { flex: 1 }]}>{line}</Text>
                  </View>
                ))}
              </View>
            ) : null
          )}
          {!!data.conclusion && (
            <View style={styles.conclusionBox}>
              <Text style={styles.aiHeading}>Kesimpulan</Text>
              <Text style={styles.bodyText}>{data.conclusion}</Text>
            </View>
          )}
        </>
      )}
    </SectionCard>
  );
}
