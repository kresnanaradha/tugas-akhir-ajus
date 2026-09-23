import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";

// Vertical bar chart for a single time series (magnitude over time) — built
// on plain Views (height % of a fixed chart area), not a charting library:
// this is a straightforward "bars grow from a baseline" case, not worth a
// new dependency for. Follows the dataviz skill's mark spec: bars capped at
// 24px thick with rounded tops, one sequential hue (a single series doesn't
// need a legend), a hairline baseline — and a per-bar hover tooltip instead
// of a value printed under every bar, so the chart stays quiet until you
// actually point at a day (onHoverIn/Out are react-native-web's mouse
// enter/leave, no extra library needed).
export function BarChart({ data, color = colors.gold, height = 120 }) {
  const [hovered, setHovered] = useState(null);
  const max = Math.max(1, ...data.map((d) => d.value));
  const lastIndex = data.length - 1;

  return (
    <View style={styles.wrap}>
      <View style={[styles.plot, { height }]}>
        {data.map((d, i) => {
          const barHeight = Math.max(2, (d.value / max) * height);
          return (
            <Pressable
              key={d.date}
              style={styles.barCol}
              onHoverIn={() => setHovered(i)}
              onHoverOut={() => setHovered((h) => (h === i ? null : h))}
            >
              {hovered === i && (
                <View style={styles.tooltip}>
                  <Text style={styles.tooltipValue}>{d.value}</Text>
                  <Text style={styles.tooltipDate}>{formatShortDate(d.date)}</Text>
                </View>
              )}
              <View style={[styles.bar, { height: barHeight, backgroundColor: color, opacity: hovered === i ? 0.8 : 1 }]} />
            </Pressable>
          );
        })}
      </View>
      <View style={styles.baseline} />
      <View style={styles.axisRow}>
        <Text style={styles.axisLabel}>{formatShortDate(data[0]?.date)}</Text>
        <Text style={styles.axisLabel}>{formatShortDate(data[lastIndex]?.date)}</Text>
      </View>
    </View>
  );
}

function formatShortDate(iso) {
  if (!iso) return "";
  return new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "short" }).format(new Date(iso));
}

const styles = StyleSheet.create({
  wrap: { gap: 4 },
  plot: { flexDirection: "row", alignItems: "flex-end", gap: 3 },
  barCol: { flex: 1, alignItems: "center", justifyContent: "flex-end" },
  bar: { width: "100%", maxWidth: 20, borderTopLeftRadius: radius.sm - 4, borderTopRightRadius: radius.sm - 4 },
  tooltip: {
    position: "absolute",
    bottom: "100%",
    marginBottom: 4,
    backgroundColor: colors.ink,
    borderRadius: radius.sm,
    paddingVertical: 4,
    paddingHorizontal: spacing.sm,
    alignItems: "center",
    ...shadow.card,
  },
  tooltipValue: { ...type.small, fontWeight: "700", color: colors.white },
  tooltipDate: { ...type.small, color: colors.white, opacity: 0.8, fontSize: 10.5 },
  baseline: { height: 1, backgroundColor: colors.border },
  axisRow: { flexDirection: "row", justifyContent: "space-between" },
  axisLabel: { ...type.small, color: colors.inkFaint },
});
