import { Feather } from "@expo/vector-icons";
import { StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";
import { currentUser } from "@/constants/mock-data";

export function TopBar() {
  return (
    <View style={styles.bar}>
      <View style={styles.search}>
        <Feather name="search" size={15} color={colors.inkFaint} />
        <TextInput
          placeholder="Cari rapat, transkrip..."
          placeholderTextColor={colors.inkFaint}
          style={styles.searchInput}
        />
      </View>

      <View style={styles.right}>
        <View style={styles.bellWrap}>
          <Feather name="bell" size={18} color={colors.inkSoft} />
          <View style={styles.badge} />
        </View>
        <View style={styles.userChip}>
          <View style={styles.avatar}>
            <Text style={styles.avatarLabel}>{currentUser.initials}</Text>
          </View>
          <View>
            <Text style={styles.userName}>{currentUser.name}</Text>
            <Text style={styles.userRole}>{currentUser.role}</Text>
          </View>
          <Feather name="chevron-down" size={14} color={colors.inkFaint} />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    height: 64,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.xl,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surface,
  },
  search: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: colors.surfaceSunken,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    height: 38,
    width: 320,
  },
  searchInput: { ...type.body, color: colors.ink, flex: 1, outlineStyle: "none" },
  right: { flexDirection: "row", alignItems: "center", gap: spacing.lg },
  bellWrap: { position: "relative" },
  badge: {
    position: "absolute",
    top: -1,
    right: -1,
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: colors.danger,
    borderWidth: 1.5,
    borderColor: colors.surface,
  },
  userChip: { flexDirection: "row", alignItems: "center", gap: 8 },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.ink,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarLabel: { color: colors.white, fontWeight: "700", fontSize: 12 },
  userName: { ...type.small, fontWeight: "600", color: colors.ink },
  userRole: { ...type.small, color: colors.inkFaint },
});
