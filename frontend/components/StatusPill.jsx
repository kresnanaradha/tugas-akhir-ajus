import { StyleSheet, Text, View } from "react-native";

import { colors, radius, type } from "@/constants/theme";

const CONFIG = {
  completed: { label: "Completed", fg: colors.success, bg: colors.successSoft },
  failed: { label: "Failed", fg: colors.danger, bg: colors.dangerSoft },
  joining: { label: "Bergabung...", fg: colors.info, bg: colors.infoSoft },
  recording: { label: "Sedang Merekam", fg: colors.danger, bg: colors.dangerSoft },
  stopping: { label: "Menghentikan...", fg: colors.info, bg: colors.infoSoft },
  processing: { label: "Memproses...", fg: colors.info, bg: colors.infoSoft },
};

export function StatusPill({ status }) {
  const cfg = CONFIG[status] || { label: status, fg: colors.inkFaint, bg: colors.surfaceSunken };
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
