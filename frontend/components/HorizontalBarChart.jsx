import { StyleSheet, Text, View } from "react-native";

import { colors, radius, type } from "@/constants/theme";

// Horizontal bars for a small part-to-whole breakdown (3 categories max at
// this app's scale — plan distribution). 1-3 series is comfortable with
// color alone per the dataviz skill, direct-labeled so nothing relies on
// color-matching against a legend.
export function HorizontalBarChart({ data }) {
  const max = Math.max(1, ...data.map((d) => d.value));

  return (
    <View style={styles.wrap}>
      {data.map((d) => (
        <View key={d.label} style={styles.row}>
          <Text style={styles.label}>{d.label}</Text>
          <View style={styles.track}>
            <View style={[styles.fill, { width: `${Math.max(2, (d.value / max) * 100)}%`, backgroundColor: d.color }]} />
          </View>
          <Text style={styles.value}>{d.value}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 10 },
  row: { flexDirection: "row", alignItems: "center", gap: 10 },
  label: { ...type.small, color: colors.inkSoft, width: 56 },
  track: { flex: 1, height: 10, borderRadius: radius.pill, backgroundColor: colors.surfaceSunken, overflow: "hidden" },
  fill: { height: "100%", borderRadius: radius.pill },
  value: { ...type.small, fontWeight: "700", color: colors.ink, width: 24, textAlign: "right" },
});
