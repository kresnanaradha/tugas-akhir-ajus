import { Feather } from "@expo/vector-icons";
import { Link } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { listMeetings } from "@/lib/api";
import { formatMeetingDate } from "@/lib/format";
import { MeetingRow } from "@/components/MeetingRow";

export default function RapatScreen() {
  const [status, setStatus] = useState("loading"); // loading | error | done
  const [meetings, setMeetings] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    listMeetings()
      .then((data) => {
        setMeetings(data.map((m) => ({ ...m, ...formatMeetingDate(m.created_at) })));
        setStatus("done");
      })
      .catch((e) => {
        setError(e.message || "Gagal memuat daftar rapat");
        setStatus("error");
      });
  }, []);

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.eyebrow}>MENU</Text>
            <View style={styles.titleRow}>
              <Text style={styles.title}>Rapat</Text>
              {status === "done" && meetings.length > 0 && (
                <View style={styles.countBadge}>
                  <Text style={styles.countBadgeLabel}>{meetings.length}</Text>
                </View>
              )}
            </View>
            <Text style={styles.description}>
              Daftar rapat yang direkam bot, transkrip otomatis, dan ringkasan AI-nya.
            </Text>
          </View>
          <Link href="/rapat/baru" asChild>
            <Pressable style={styles.newButton}>
              <Feather name="plus" size={14} color={colors.ink} />
              <Text style={styles.newButtonLabel}>Rapat Baru</Text>
            </Pressable>
          </Link>
        </View>

        <View style={styles.panel}>
          {status === "loading" && (
            <View style={styles.stateBox}>
              <ActivityIndicator color={colors.gold} />
              <Text style={styles.stateText}>Memuat daftar rapat...</Text>
            </View>
          )}

          {status === "error" && (
            <View style={styles.stateBox}>
              <Feather name="alert-circle" size={20} color={colors.danger} />
              <Text style={styles.stateText}>{error}</Text>
            </View>
          )}

          {status === "done" && meetings.length === 0 && (
            <View style={styles.stateBox}>
              <Feather name="inbox" size={20} color={colors.inkFaint} />
              <Text style={styles.stateText}>
                Belum ada rapat yang direkam. Mulai dari "Rapat Baru" atau "Upload Audio" di dashboard.
              </Text>
            </View>
          )}

          {status === "done" && meetings.map((meeting) => <MeetingRow key={meeting.id} meeting={meeting} />)}
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { alignItems: "center", padding: spacing.xxl },
  content: { gap: spacing.xl, maxWidth: 900, width: "100%" },

  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: spacing.lg },
  eyebrow: { ...type.eyebrow, color: colors.inkFaint },
  titleRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: 4 },
  title: { ...type.display, color: colors.ink },
  countBadge: {
    backgroundColor: colors.goldSoft,
    borderRadius: radius.pill,
    paddingVertical: 3,
    paddingHorizontal: 10,
  },
  countBadgeLabel: { ...type.small, fontWeight: "700", color: colors.goldDeep },
  description: { ...type.body, color: colors.inkSoft, marginTop: 2, maxWidth: 60 * 8 },

  newButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    backgroundColor: colors.gold,
    paddingVertical: 10,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.sm,
    ...shadow.card,
  },
  newButtonLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },

  panel: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: "hidden",
    ...shadow.card,
  },
  stateBox: { alignItems: "center", gap: spacing.sm, padding: spacing.xxl },
  stateText: { ...type.body, color: colors.inkSoft, textAlign: "center" },
});
