import { StyleSheet, Text, View } from "react-native";

import { colors, radius, type } from "@/constants/theme";

const CONFIG = {
  completed: { label: "Completed", fg: colors.success, bg: colors.successSoft },
  processing: { label: "Processing", fg: colors.info, bg: colors.infoSoft },
  failed: { label: "Failed", fg: colors.danger, bg: colors.dangerSoft },
};

export function StatusPill({ status }) {
  const cfg = CONFIG[status];
  return (
    <View style={[styles.pill, { backgroundColor: cfg.bg }]}>
      <View style={[styles.dot, { backgroundColor: cfg.fg }]} />
      <Text style={[styles.label, { color: cfg.fg }]}>{cfg.label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingVertical: 5,
    paddingHorizontal: 10,
    borderRadius: radius.pill,
    alignSelf: "flex-start",
  },
  dot: { width: 6, height: 6, borderRadius: 3 },
  label: { ...type.small, fontWeight: "600" },
});
