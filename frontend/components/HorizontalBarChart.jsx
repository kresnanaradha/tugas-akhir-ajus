import { StyleSheet, Text, View } from "react-native";

import { colors, radius, type } from "@/constants/theme";

// batang horizontal untuk rincian kecil (paling banyak 3 kategori di sini), tiap baris diberi label langsung supaya tidak bergantung pada legenda.
// fill menyebar barisnya ke seluruh tinggi kartu yang diregangkan sampai setinggi tetangganya
export function HorizontalBarChart({ data, labelWidth = 56, unit = "", fill = false }) {
  const max = Math.max(1, ...data.map((d) => d.value));

  return (
    <View style={[styles.wrap, fill && styles.fill_]}>
      {data.map((d) => (
        <View key={d.label} style={styles.row}>
          <Text style={[styles.label, { width: labelWidth }]} numberOfLines={1}>{d.label}</Text>
          <View style={styles.track}>
            <View style={[styles.fill, { width: `${Math.max(2, (d.value / max) * 100)}%`, backgroundColor: d.color }]} />
          </View>
          <Text style={[styles.value, unit && { width: 70 }]}>{d.value}{unit ? ` ${unit}` : ""}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 10 },
  fill_: { flex: 1, justifyContent: "space-evenly" },
  row: { flexDirection: "row", alignItems: "center", gap: 10 },
  label: { ...type.small, fontSize: 13.5, color: colors.inkSoft, width: 56 },
  track: { flex: 1, height: 14, borderRadius: radius.pill, backgroundColor: colors.surfaceSunken, overflow: "hidden" },
  fill: { height: "100%", borderRadius: radius.pill },
  value: { ...type.small, fontWeight: "700", color: colors.ink, width: 24, textAlign: "right" },
});
