import { Feather } from "@expo/vector-icons";
import { Link } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { getReportActionItems, getReportExportUrl, getReportStats, toggleActionItem } from "@/lib/api";
import { BarChart } from "@/components/BarChart";
import { HorizontalBarChart } from "@/components/HorizontalBarChart";
import { StatCard } from "@/components/StatCard";

// Same fixed categorical order as admin.jsx's PLAN_COLORS, same reasoning —
// one consistent color per category across the whole app instead of each
// chart inventing its own.
const PLATFORM_COLORS = { google_meet: colors.info, zoom: colors.success, upload: colors.goldDeep };
const PLATFORM_LABELS = { google_meet: "Google Meet", zoom: "Zoom", upload: "Upload" };

export default function LaporanScreen() {
  const [status, setStatus] = useState("loading"); // loading | error | done
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [actions, setActions] = useState(null); // null = loading, false = failed

  useEffect(() => {
    getReportStats()
      .then((data) => {
        setStats(data);
        setStatus("done");
      })
      .catch((e) => {
        setError(e.message || "Gagal memuat laporan");
        setStatus("error");
      });
  }, []);

  useEffect(() => {
    getReportActionItems()
      .then(setActions)
      .catch(() => setActions(false));
  }, []);

  // Rows here come from every meeting's own action_items array (via
  // meeting_id + index, see GET /reports/action-items), not just this one
  // meeting — so unlike the meeting detail page, marking one done here also
  // has to update this rollup's own counts locally (an open item leaving the
  // "Belum Selesai" list, its assignee's open/done split shifting) instead
  // of just flipping one flag. Optimistic, reverted on failure.
  function markDone(item) {
    setActions((a) => ({
      ...a,
      done: a.done + 1,
      open: a.open - 1,
      open_items: a.open_items.filter((it) => it !== item),
      by_assignee: a.by_assignee.map((r) =>
        r.assignee === (item.assignee || "Belum ditentukan") ? { ...r, open: r.open - 1, done: r.done + 1 } : r
      ),
    }));
    toggleActionItem(item.meeting_id, item.index, true).catch(() => {
      // Reverts by putting it back at the end of the list — exact original
      // order isn't worth tracking for a failure path that should be rare.
      setActions((a) => ({
        ...a,
        done: a.done - 1,
        open: a.open + 1,
        open_items: [...a.open_items, item],
        by_assignee: a.by_assignee.map((r) =>
          r.assignee === (item.assignee || "Belum ditentukan") ? { ...r, open: r.open + 1, done: r.done - 1 } : r
        ),
      }));
    });
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <View style={styles.headerRow}>
          <View>
            <Text style={styles.eyebrow}>LAPORAN</Text>
            <Text style={styles.title}>Aktivitas Rapat Anda</Text>
            <Text style={styles.description}>Ringkasan rapat, durasi, dan platform yang Anda pakai.</Text>
          </View>
          <Pressable style={styles.exportButton} onPress={() => window.open(getReportExportUrl(), "_blank")}>
            <Feather name="download" size={14} color={colors.ink} />
            <Text style={styles.exportButtonLabel}>Export Laporan (PDF)</Text>
          </Pressable>
        </View>

        {status === "loading" && (
          <View style={styles.stateBox}>
            <ActivityIndicator color={colors.gold} />
          </View>
        )}

        {status === "error" && (
          <View style={styles.stateBox}>
            <Feather name="alert-circle" size={20} color={colors.danger} />
            <Text style={styles.stateText}>{error}</Text>
          </View>
        )}

        {status === "done" && stats && (
          <View style={styles.columns}>
            <View style={styles.column}>
              <Text style={styles.sectionLabel}>Volume Rapat</Text>
              <View style={styles.statRow}>
                <StatCard value={stats.meetings.today} label="Hari Ini" />
                <StatCard value={stats.meetings.this_week} label="Minggu Ini" />
                <StatCard value={stats.meetings.this_month} label="Bulan Ini" />
                <StatCard value={stats.meetings.total} label="Total" />
              </View>
              <View style={styles.chartCard}>
                <Text style={styles.chartTitle}>Rapat per Hari (14 Hari Terakhir)</Text>
                <BarChart data={stats.meetings_daily.map((d) => ({ date: d.date, value: d.count }))} />
              </View>
            </View>

            <View style={styles.column}>
              <Text style={styles.sectionLabel}>Rekaman</Text>
              <View style={styles.statRow}>
                <StatCard value={`${(stats.total_duration_minutes / 60).toFixed(1)} jam`} label="Total Durasi Rekaman" />
                <StatCard
                  value={`${Math.round((stats.meetings.completed / (stats.meetings.total || 1)) * 100)}%`}
                  label="Tingkat Keberhasilan"
                  delta={`${stats.meetings.failed} gagal`}
                  deltaColor={colors.danger}
                />
              </View>
              <View style={styles.chartCard}>
                <Text style={styles.chartTitle}>Distribusi Platform</Text>
                <HorizontalBarChart
                  data={Object.entries(stats.platform_counts).map(([platform, n]) => ({
                    label: PLATFORM_LABELS[platform] || platform,
                    value: n,
                    color: PLATFORM_COLORS[platform] || colors.inkFaint,
                  }))}
                />
              </View>
            </View>
          </View>
        )}

        <Text style={styles.sectionLabel}>Tindak Lanjut (Action Item)</Text>
        {actions === null && (
          <View style={styles.stateBox}>
            <ActivityIndicator color={colors.gold} />
            <Text style={styles.stateText}>Menghitung action item dari semua rapat...</Text>
          </View>
        )}
        {actions === false && <Text style={styles.stateText}>Gagal memuat rekap action item.</Text>}
        {actions && (
          <View style={styles.columns}>
            <View style={styles.column}>
              <View style={styles.statRow}>
                <StatCard value={actions.total} label="Total Action Item" />
                <StatCard value={actions.done} label="Selesai" delta={`${Math.round((actions.done / (actions.total || 1)) * 100)}%`} deltaColor={colors.success} />
                <StatCard value={actions.open} label="Belum Selesai" deltaColor={colors.danger} />
              </View>
              <View style={styles.chartCard}>
                <Text style={styles.chartTitle}>Per Penanggung Jawab</Text>
                {actions.by_assignee.length === 0 ? (
                  <Text style={styles.stateText}>Belum ada action item.</Text>
                ) : (
                  <HorizontalBarChart
                    data={actions.by_assignee.slice(0, 8).map((r) => ({
                      label: r.assignee,
                      value: r.open + r.done,
                      color: r.open > 0 ? colors.goldDeep : colors.success,
                    }))}
                  />
                )}
              </View>
            </View>

            <View style={styles.column}>
              <View style={[styles.chartCard, { flex: 1 }]}>
                <Text style={styles.chartTitle}>Belum Selesai ({actions.open})</Text>
                <ScrollView style={{ maxHeight: 360 }} contentContainerStyle={{ gap: 2 }}>
                  {actions.open_items.length === 0 && <Text style={styles.stateText}>Semua action item sudah selesai.</Text>}
                  {actions.open_items.map((it, i) => (
                    <View key={i} style={styles.openRow}>
                      <Pressable onPress={() => markDone(it)} hitSlop={8}>
                        <Feather name="square" size={13} color={colors.inkFaint} style={{ marginTop: 3 }} />
                      </Pressable>
                      <Link href={`/rapat/${it.meeting_id}`} asChild>
                        <Pressable style={styles.openRowLink}>
                          <View style={{ flex: 1 }}>
                            <Text style={styles.openTask}>{it.task}</Text>
                            <Text style={styles.openMeta} numberOfLines={1}>
                              {[it.assignee, it.due, it.meeting_title].filter(Boolean).join(" · ")}
                            </Text>
                          </View>
                          <Feather name="chevron-right" size={13} color={colors.inkFaint} />
                        </Pressable>
                      </Link>
                    </View>
                  ))}
                </ScrollView>
              </View>
            </View>
          </View>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { alignItems: "center", paddingVertical: spacing.lg, paddingHorizontal: "5%" },
  content: { gap: spacing.md, width: "100%" },

  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: spacing.lg },
  eyebrow: { ...type.eyebrow, color: colors.inkFaint },
  title: { ...type.h1, fontSize: 24, color: colors.ink, marginTop: 4 },
  description: { ...type.body, color: colors.inkSoft, marginTop: 2, maxWidth: 60 * 8 },

  exportButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    backgroundColor: colors.gold,
    paddingVertical: 8,
    paddingHorizontal: spacing.md,
    borderRadius: radius.sm,
    ...shadow.card,
  },
  exportButtonLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },

  columns: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, alignItems: "flex-start" },
  column: { flex: 1, minWidth: 380, gap: spacing.md },
  openRow: { flexDirection: "row", gap: 8, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.border },
  openTask: { ...type.small, fontSize: 13.5, color: colors.ink, lineHeight: 18 },
  openMeta: { ...type.small, color: colors.inkFaint },
  sectionLabel: { ...type.eyebrow, color: colors.inkFaint, marginTop: spacing.md },
  statRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },

  chartCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.md,
    ...shadow.card,
  },
  chartTitle: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },

  stateBox: { alignItems: "center", gap: spacing.sm, padding: spacing.xl },
  stateText: { ...type.body, color: colors.inkSoft, textAlign: "center" },
});
