import { Feather } from "@expo/vector-icons";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";

// No real auth/team backend yet (see CLAUDE.md's "Known POC gaps") — every
// account is effectively individual-only right now, so this always shows
// the empty state. Notulis isn't team-only: an individual is a fully valid
// way to use it (record/transcribe/summarize solo), a team is opt-in on
// top of that, not a requirement — hence no upsell pressure here, just a
// plain "you don't have one yet" plus the (not-yet-wired) way to get one.
export default function TeamScreen() {
  return (
    <View style={styles.screen}>
      <View style={styles.content}>
        <Text style={styles.eyebrow}>MENU</Text>
        <Text style={styles.title}>Team</Text>
        <Text style={styles.description}>Kelola anggota tim dan hak akses.</Text>

        <View style={styles.emptyCard}>
          <View style={styles.iconWrap}>
            <Feather name="users" size={22} color={colors.goldDeep} />
          </View>
          <Text style={styles.emptyTitle}>Anda Belum Memiliki Team</Text>
          <Text style={styles.emptyBody}>
            Notulis tetap bisa dipakai sendirian — rapat, transkrip, dan ringkasan tersimpan di akun Anda. Team cuma
            perlu kalau mau berbagi hasil rapat dan kelola anggota bareng orang lain.
          </Text>
          <Pressable style={styles.createButton} disabled>
            <Feather name="plus" size={14} color={colors.inkFaint} />
            <Text style={styles.createButtonLabel}>Buat Team (Segera Hadir)</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, alignItems: "center", padding: spacing.lg },
  content: { gap: spacing.sm, maxWidth: 720, width: "100%" },
  eyebrow: { ...type.eyebrow, color: colors.inkFaint },
  title: { ...type.h1, fontSize: 24, color: colors.ink, marginTop: 4 },
  description: { ...type.body, color: colors.inkSoft, marginTop: 2, marginBottom: spacing.xl },

  emptyCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
    alignItems: "center",
    gap: spacing.sm,
  },
  iconWrap: {
    width: 48,
    height: 48,
    borderRadius: radius.sm,
    backgroundColor: colors.goldSoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xs,
  },
  emptyTitle: { ...type.h2, color: colors.ink, textAlign: "center" },
  emptyBody: { ...type.body, color: colors.inkFaint, textAlign: "center", lineHeight: 20, maxWidth: 420 },

  createButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: 8,
    paddingHorizontal: spacing.md,
    marginTop: spacing.sm,
    opacity: 0.6,
  },
  createButtonLabel: { ...type.bodyMedium, fontWeight: "600", color: colors.inkFaint },
});
