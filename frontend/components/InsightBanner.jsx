import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";

export function InsightBanner({ eyebrow, headline, detail, ctaLabel, onPressCta }) {
  return (
    <View style={styles.banner}>
      <View style={styles.ring1} />
      <View style={styles.ring2} />
      <Text style={styles.eyebrow}>{eyebrow}</Text>
      <Text style={styles.headline}>{headline}</Text>
      <Text style={styles.detail}>{detail}</Text>
      <Pressable style={styles.cta} onPress={onPressCta}>
        <Text style={styles.ctaLabel}>{ctaLabel}</Text>
        <Text style={styles.ctaArrow}>↗</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: colors.gold,
    borderRadius: radius.lg,
    padding: spacing.xl,
    gap: 6,
    overflow: "hidden",
    position: "relative",
  },
  ring1: {
    position: "absolute",
    right: -20,
    top: -30,
    width: 130,
    height: 130,
    borderRadius: 65,
    borderWidth: 1,
    borderColor: "rgba(27,31,43,0.15)",
  },
  ring2: {
    position: "absolute",
    right: 30,
    top: 30,
    width: 70,
    height: 70,
    borderRadius: 35,
    backgroundColor: "rgba(27,31,43,0.08)",
  },
  eyebrow: { ...type.eyebrow, color: colors.goldDeep, textTransform: "uppercase" },
  headline: { ...type.h1, color: colors.ink, marginTop: 6, maxWidth: 460 },
  detail: { ...type.body, color: colors.inkSoft, marginTop: 2, maxWidth: 460 },
  cta: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: colors.ink,
    alignSelf: "flex-start",
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: radius.sm,
    marginTop: spacing.md,
  },
  ctaLabel: { ...type.bodyMedium, color: colors.white },
  ctaArrow: { color: colors.white, fontSize: 13 },
});
