import { Feather } from "@expo/vector-icons";
import { router } from "expo-router";
import { Pressable, StyleSheet, Text } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";

// Real "back" (wherever the user actually came from — a dashboard list, a
// search result, the rapat list, ...), not a hardcoded destination. Falls
// back to `fallbackHref` only when there's no navigation history to go back
// to (e.g. this page was opened directly via a pasted link or a refresh).
export function BackLink({ label = "Kembali", fallbackHref = "/rapat" }) {
  return (
    <Pressable
      onPress={() => (router.canGoBack() ? router.back() : router.replace(fallbackHref))}
      style={({ pressed }) => [styles.link, pressed && styles.linkActive]}
    >
      <Feather name="chevron-left" size={15} color={colors.inkSoft} />
      <Text style={styles.label}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  link: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    alignSelf: "flex-start",
    marginBottom: spacing.md,
    paddingVertical: 7,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    ...shadow.card,
  },
  linkActive: { backgroundColor: colors.surfaceSunken, borderColor: colors.inkFaint },
  label: { ...type.small, fontWeight: "600", color: colors.inkSoft },
});
