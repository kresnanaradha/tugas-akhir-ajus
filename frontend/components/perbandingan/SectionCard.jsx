// kartu berjudul untuk satu bagian rapat (topik, keputusan, ringkasan...), dipakai baris perbandingan dan kartu AI
import { Feather } from "@expo/vector-icons";
import { Text, View } from "react-native";
import { styles } from "@/components/perbandingan/styles";
import { colors } from "@/constants/theme";

export function SectionCard({ icon, title, count, children }) {
  return (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <View style={styles.cardIcon}>
          <Feather name={icon} size={13} color={colors.goldDeep} />
        </View>
        <Text style={styles.cardTitle}>{title}</Text>
        {count != null && (
          <View style={styles.countBadge}>
            <Text style={styles.countBadgeLabel}>{count}</Text>
          </View>
        )}
      </View>
      {children}
    </View>
  );
}
