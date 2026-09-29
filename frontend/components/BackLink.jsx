import { Feather } from "@expo/vector-icons";
import { router } from "expo-router";
import { Pressable, StyleSheet, Text } from "react-native";

import { colors, spacing, type } from "@/constants/theme";

// Real "back" (wherever the user actually came from — a dashboard list, a
// search result, the rapat list, ...), not a hardcoded destination. Falls
// back to `fallbackHref` only when there's no navigation history to go back
// to (e.g. this page was opened directly via a pasted link or a refresh).
export function BackLink({ label = "Kembali", fallbackHref = "/rapat" }) {
  return (
    <Pressable
      onPress={() => (router.canGoBack() ? router.back() : router.replace(fallbackHref))}
      style={styles.link}
    >
      <Feather name="chevron-left" size={14} color={colors.inkSoft} />
      <Text style={styles.label}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  link: { flexDirection: "row", alignItems: "center", gap: 2, marginBottom: spacing.md, alignSelf: "flex-start" },
  label: { ...type.small, color: colors.inkSoft },
});
