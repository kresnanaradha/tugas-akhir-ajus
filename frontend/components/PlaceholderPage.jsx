import { Feather } from "@expo/vector-icons";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";

export function PlaceholderPage({ icon, title, description, comingFeatures }) {
  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <Text style={styles.eyebrow}>MENU</Text>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.description}>{description}</Text>

        <View style={styles.card}>
          <View style={styles.iconWrap}>
            <Feather name={icon} size={22} color={colors.goldDeep} />
          </View>
          <Text style={styles.cardTitle}>Halaman ini sedang dibangun</Text>
          <Text style={styles.cardBody}>
            Tampilan di sini masih rangka UI dengan data contoh — belum tersambung ke backend. Fitur yang direncanakan:
          </Text>
          <View style={styles.featureList}>
            {comingFeatures.map((feature) => (
              <View key={feature} style={styles.featureRow}>
                <View style={styles.featureDot} />
                <Text style={styles.featureLabel}>{feature}</Text>
              </View>
            ))}
          </View>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { alignItems: "center", padding: spacing.xxl },
  content: { gap: spacing.sm, maxWidth: 720, width: "100%" },
  eyebrow: { ...type.eyebrow, color: colors.inkFaint },
  title: { ...type.display, color: colors.ink, marginTop: 4 },
  description: { ...type.body, color: colors.inkSoft, marginTop: 2, marginBottom: spacing.xl, maxWidth: 60 * 8 },

  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.xl,
    gap: spacing.sm,
  },
  iconWrap: {
    width: 44,
    height: 44,
    borderRadius: radius.sm,
    backgroundColor: colors.goldSoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  cardTitle: { ...type.h2, color: colors.ink },
  cardBody: { ...type.body, color: colors.inkFaint, marginBottom: spacing.sm },
  featureList: { gap: spacing.sm },
  featureRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  featureDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: colors.inkFaint },
  featureLabel: { ...type.body, color: colors.ink },
});
