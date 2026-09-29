import { Feather } from "@expo/vector-icons";
import { Link, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";
import { getMeeting, listMeetings } from "@/lib/api";
import { formatMeetingDate } from "@/lib/format";
import { useAuth } from "@/lib/auth-context";
import { InsightBanner } from "@/components/InsightBanner";
import { MeetingRow } from "@/components/MeetingRow";
import { StatCard } from "@/components/StatCard";

function greetingWord() {
  const hour = new Date().getHours();
  if (hour < 11) return "pagi";
  if (hour < 15) return "siang";
  if (hour < 19) return "sore";
  return "malam";
}

// href: null = not wired to a page yet.
const QUICK_ACTIONS = [
  { icon: "video", label: "Rapat Baru", note: "Bot join otomatis", href: "/rapat/baru" },
  { icon: "upload", label: "Upload", note: "Transkripsi file lama", href: "/rapat/upload" },
  { icon: "shuffle", label: "Bandingkan Rapat", note: "AI side-by-side", href: "/perbandingan" },
  { icon: "search", label: "Knowledge Base", note: "Tanya dari rapat", href: "/knowledge-base" },
];

const todayLabel = new Intl.DateTimeFormat("id-ID", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
}).format(new Date());

// The banner's content, from the newest finished meeting's stored summary (no
// extra AI call): its still-open action items first, else its key decisions.
function buildInsight(meeting, summary) {
  const open = (summary?.action_items || []).filter((a) => !a.done);
  const short = (t, n) => (t.length > n ? `${t.slice(0, n).trim()}...` : t);
  if (open.length > 0) {
    const first = open[0];
    const who = [first.assignee, first.due].filter(Boolean).join(", ");
    return {
      headline: `${open.length} action item belum selesai`,
      detail: `${meeting.title}: ${short(first.task, 110)}${who ? ` (${who})` : ""}${open.length > 1 ? ` dan ${open.length - 1} lainnya` : ""}`,
      cta: "Buka Rapat",
      href: `/rapat/${meeting.id}`,
    };
  }
  const decision = summary?.key_decisions?.[0];
  if (decision) {
    return { headline: "Keputusan dari rapat terakhir", detail: `${meeting.title}: ${short(decision, 140)}`, cta: "Buka Rapat", href: `/rapat/${meeting.id}` };
  }
  return {
    headline: "Belum ada insight",
    detail: "Insight muncul setelah rapat selesai diproses dan punya ringkasan.",
    cta: "Mulai Rapat",
    href: "/rapat/baru",
  };
}

export default function DashboardScreen() {
  const router = useRouter();
  const [insight, setInsight] = useState(null);
  const { user } = useAuth();
  const [meetingsStatus, setMeetingsStatus] = useState("loading"); // loading | error | done
  const [meetings, setMeetings] = useState([]);

  useEffect(() => {
    listMeetings()
      .then((data) => {
        setMeetings(data.map((m) => ({ ...m, ...formatMeetingDate(m.created_at) })));
        setMeetingsStatus("done");
      })
      .catch(() => setMeetingsStatus("error"));
  }, []);

  useEffect(() => {
    if (meetingsStatus !== "done") return;
    const latest = meetings.find((m) => m.status === "completed" && m.recording);
    if (!latest) {
      setInsight(buildInsight({}, null));
      return;
    }
    getMeeting(latest.id)
      .then((m) => setInsight(buildInsight(latest, m.summary)))
      .catch(() => setInsight(buildInsight(latest, null)));
  }, [meetingsStatus]);

  const total = meetings.length;
  const completed = meetings.filter((m) => m.status === "completed").length;
  const failed = meetings.filter((m) => m.status === "failed").length;
  const totalDurationHours = (meetings.reduce((sum, m) => sum + (m.duration_minutes || 0), 0) / 60).toFixed(1);
  const successRate = total > 0 ? `${Math.round((completed / total) * 100)}% sukses` : null;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <View style={styles.headerRow}>
          <View>
            <Text style={styles.dateLabel}>{todayLabel.toUpperCase()}</Text>
            <Text style={styles.greeting}>Selamat {greetingWord()}, {(user?.name || "").split(" ")[0]}.</Text>
          </View>
          <View style={styles.headerActions}>
            <Link href="/rapat/upload" asChild>
              <Pressable style={styles.secondaryButton}>
                <Feather name="upload" size={14} color={colors.ink} />
                <Text style={styles.secondaryButtonLabel}>Upload</Text>
              </Pressable>
            </Link>
            <Link href="/rapat/baru" asChild>
              <Pressable style={styles.primaryButton}>
                <Feather name="plus" size={14} color={colors.ink} />
                <Text style={styles.primaryButtonLabel}>Mulai Rapat</Text>
              </Pressable>
            </Link>
          </View>
        </View>

        <InsightBanner
          eyebrow="Insight dari rapat terakhir"
          headline={insight?.headline || "Memuat insight..."}
          detail={insight?.detail || " "}
          ctaLabel={insight?.cta || "Buka Rapat"}
          onPressCta={() => insight && router.push(insight.href)}
        />
        <View style={styles.statGrid}>
          <StatCard value={String(total)} label="Total Rapat" />
          <StatCard value={`${totalDurationHours}j`} label="Total Durasi" />
          <StatCard value={String(completed)} label="Transkrip" delta={successRate} deltaColor={colors.goldDeep} />
          <StatCard value={String(failed)} label="Rapat Gagal" deltaColor={colors.danger} />
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
              {meetingsStatus === "loading" && (
                <View style={styles.meetingsState}>
                  <ActivityIndicator color={colors.gold} />
                </View>
              )}
              {meetingsStatus === "error" && (
                <View style={styles.meetingsState}>
                  <Text style={styles.meetingsStateText}>Gagal memuat daftar rapat.</Text>
                </View>
              )}
              {meetingsStatus === "done" && meetings.length === 0 && (
                <View style={styles.meetingsState}>
                  <Text style={styles.meetingsStateText}>Belum ada rapat yang direkam.</Text>
                </View>
              )}
              {meetingsStatus === "done" &&
                meetings.slice(0, 5).map((meeting) => <MeetingRow key={meeting.id} meeting={meeting} />)}
            </View>
          </View>

          <View style={styles.sideCol}>
          <View style={styles.sidePanel}>
            <Text style={styles.panelTitle}>Aksi Cepat</Text>
            <View style={styles.actionList}>
              {QUICK_ACTIONS.map((action) => (
                <Link key={action.label} href={action.href} asChild>
                  <Pressable style={styles.actionRow}>
                    <View style={styles.actionIcon}>
                      <Feather name={action.icon} size={15} color={colors.ink} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.actionLabel}>{action.label}</Text>
                      <Text style={styles.actionNote}>{action.note}</Text>
                    </View>
                    <Feather name="chevron-right" size={14} color={colors.inkFaint} />
                  </Pressable>
                </Link>
              ))}
            </View>
          </View>
          </View>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { alignItems: "center", padding: spacing.lg },
  content: { gap: spacing.md, maxWidth: 1200, width: "100%" },

  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end" },
  dateLabel: { ...type.eyebrow, color: colors.inkFaint },
  greeting: { ...type.h1, fontSize: 24, color: colors.ink, marginTop: 2 },
  headerActions: { flexDirection: "row", gap: spacing.sm },

  secondaryButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    paddingVertical: 8,
    paddingHorizontal: spacing.md,
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

  statGrid: { flexDirection: "row", gap: spacing.md },

  mainGrid: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start" },

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
  meetingsState: { padding: spacing.xl, alignItems: "center" },
  meetingsStateText: { ...type.body, color: colors.inkFaint },

  sideCol: { flex: 1, gap: spacing.md },
  sidePanel: {
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
