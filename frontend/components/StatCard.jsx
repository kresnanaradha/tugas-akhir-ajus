import { StyleSheet, Text, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";

export function StatCard({ value, label, delta, deltaColor = colors.inkFaint, style }) {
  return (
    <View style={[styles.card, style]}>
      <Text style={styles.value} numberOfLines={1} ellipsizeMode="tail">
        {value}
      </Text>
      <Text style={styles.label}>{label}</Text>
      {delta ? <Text style={[styles.delta, { color: deltaColor }]}>{delta}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    // tanpa minimum, kartu yang diperas di kolom sempit memecah angka seperti "Rp 99.000" di tengah digit alih-alih barisnya yang membungkus
    minWidth: 150,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.lg,
    gap: 4,
    justifyContent: "center", // kartu yang diregangkan setinggi tetangga yang lebih tinggi tetap menaruh teksnya di tengah
    ...shadow.card,
  },
  value: { ...type.stat, fontSize: 34, lineHeight: 40, color: colors.ink, fontVariant: ["tabular-nums"] },
  label: { ...type.small, color: colors.inkSoft },
  delta: { ...type.small, fontWeight: "600", marginTop: 2 },
});
