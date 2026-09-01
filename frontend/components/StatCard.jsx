import { StyleSheet, Text, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";

export function StatCard({ value, label, delta, deltaColor = colors.inkFaint }) {
  return (
    <View style={styles.card}>
      <Text style={styles.value}>{value}</Text>
      <Text style={styles.label}>{label}</Text>
      {delta ? <Text style={[styles.delta, { color: deltaColor }]}>{delta}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.lg,
    gap: 4,
    ...shadow.card,
  },
  value: { ...type.stat, color: colors.ink, fontVariant: ["tabular-nums"] },
  label: { ...type.small, color: colors.inkSoft },
  delta: { ...type.small, fontWeight: "600", marginTop: 2 },
});
