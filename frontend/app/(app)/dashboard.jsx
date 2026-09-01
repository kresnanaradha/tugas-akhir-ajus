import { Feather } from "@expo/vector-icons";
import { Link } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";
import { aiInsight, dashboardStats, meetings } from "@/constants/mock-data";
import { InsightBanner } from "@/components/InsightBanner";
import { MeetingRow } from "@/components/MeetingRow";
import { StatCard } from "@/components/StatCard";

const QUICK_ACTIONS = [
  { icon: "video", label: "Rapat Baru", note: "Bot join otomatis" },
  { icon: "upload", label: "Upload Audio", note: "Transkripsi file lama" },
  { icon: "shuffle", label: "Bandingkan Rapat", note: "AI side-by-side" },
  { icon: "search", label: "Knowledge Base", note: "Tanya dari rapat" },
];

const todayLabel = new Intl.DateTimeFormat("id-ID", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
}).format(new Date());

export default function DashboardScreen() {
  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
    <View style={styles.content}>
      <View style={styles.headerRow}>
        <View>
          <Text style={styles.dateLabel}>{todayLabel.toUpperCase()}</Text>
          <Text style={styles.greeting}>Selamat pagi, Ahmad.</Text>
        </View>
        <View style={styles.headerActions}>
          <Pressable style={styles.secondaryButton}>
            <Feather name="upload" size={14} color={colors.ink} />
            <Text style={styles.secondaryButtonLabel}>Upload Audio</Text>
          </Pressable>
          <Pressable style={styles.primaryButton}>
            <Feather name="plus" size={14} color={colors.ink} />
            <Text style={styles.primaryButtonLabel}>Mulai Rapat</Text>
          </Pressable>
        </View>
      </View>

      <InsightBanner
        eyebrow="AI Insight hari ini"
        headline={aiInsight.headline}
        detail={`${aiInsight.detail} · ${aiInsight.metric}`}
        ctaLabel="Tanya Knowledge Base"
      />

      <View style={styles.statGrid}>
        <StatCard value={String(dashboardStats.totalMeetings)} label="Total Rapat" delta={dashboardStats.totalMeetingsDelta} deltaColor={colors.info} />
        <StatCard value={`${dashboardStats.totalDurationHours}j`} label="Total Durasi" delta={dashboardStats.totalDurationDelta} deltaColor={colors.success} />
        <StatCard value={String(dashboardStats.transcriptCount)} label="Transkrip" delta={dashboardStats.transcriptSuccessRate} deltaColor={colors.goldDeep} />
        <StatCard
          value={String(dashboardStats.activeMembers)}
          label="Anggota Aktif"
          delta={`dari ${dashboardStats.totalMembers} total`}
        />
      </View>

      <View style={styles.mainGrid}>
        <View style={styles.meetingsPanel}>
          <View style={styles.panelHeader}>
            <Text style={styles.panelTitle}>Rapat Terbaru</Text>
            <Link href="/rapat" asChild>
              <Pressable style={styles.panelLinkRow}>
                <Text style={styles.panelLink}>Lihat semua</Text>
                <Feather name="chevron-right" size={14} color={colors.info} />
              </Pressable>
            </Link>
          </View>
          <View style={styles.meetingsList}>
            {meetings.map((meeting) => (
              <MeetingRow key={meeting.id} meeting={meeting} />
            ))}
          </View>
        </View>

        <View style={styles.sidePanel}>
          <Text style={styles.panelTitle}>Aksi Cepat</Text>
          <View style={styles.actionList}>
            {QUICK_ACTIONS.map((action) => (
              <Pressable key={action.label} style={styles.actionRow}>
                <View style={styles.actionIcon}>
                  <Feather name={action.icon} size={15} color={colors.ink} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.actionLabel}>{action.label}</Text>
                  <Text style={styles.actionNote}>{action.note}</Text>
                </View>
                <Feather name="chevron-right" size={14} color={colors.inkFaint} />
              </Pressable>
            ))}
          </View>
        </View>
      </View>
    </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { alignItems: "center", padding: spacing.xxl },
  content: { gap: spacing.xl, maxWidth: 1200, width: "100%" },

  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end" },
  dateLabel: { ...type.eyebrow, color: colors.inkFaint },
  greeting: { ...type.display, color: colors.ink, marginTop: 4 },
  headerActions: { flexDirection: "row", gap: spacing.sm },

  secondaryButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    paddingVertical: 10,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.sm,
  },
  secondaryButtonLabel: { ...type.bodyMedium, color: colors.ink },
  primaryButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    backgroundColor: colors.gold,
    paddingVertical: 10,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.sm,
  },
  primaryButtonLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },

  statGrid: { flexDirection: "row", gap: spacing.lg },

  mainGrid: { flexDirection: "row", gap: spacing.lg, alignItems: "flex-start" },

  meetingsPanel: {
    flex: 2.4,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: "hidden",
  },
  panelHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  panelTitle: { ...type.eyebrow, color: colors.inkFaint, textTransform: "uppercase" },
  panelLinkRow: { flexDirection: "row", alignItems: "center", gap: 2 },
  panelLink: { ...type.small, color: colors.info, fontWeight: "600" },
  meetingsList: {},

  sidePanel: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.md,
  },
  actionList: { gap: 2 },
  actionRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.sm,
  },
  actionIcon: {
    width: 34,
    height: 34,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceSunken,
    alignItems: "center",
    justifyContent: "center",
  },
  actionLabel: { ...type.bodyMedium, color: colors.ink },
  actionNote: { ...type.small, color: colors.inkFaint },
});
