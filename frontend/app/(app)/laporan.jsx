import { Feather } from "@expo/vector-icons";
import { Link } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { getReportActionItems, getReportExportUrl, getReportStats, getReportTeam, toggleActionItem } from "@/lib/api";
import { BarChart } from "@/components/BarChart";
import { HorizontalBarChart } from "@/components/HorizontalBarChart";
import { StatCard } from "@/components/StatCard";

// satu warna tetap per platform, ide yang sama dengan warna paket di admin.jsx
const PLATFORM_COLORS = { google_meet: colors.info, zoom: colors.success, upload: colors.goldDeep };
const PLATFORM_LABELS = { google_meet: "Google Meet", zoom: "Zoom", upload: "Upload" };

// Tanggal di bawah tiap angka Volume Rapat. Minggu berjalan Senin sampai Minggu, sama
// dengan date_trunc('week') server yang menghasilkan hitungannya.
function volumeDates() {
  const fmt = (d, o) => new Intl.DateTimeFormat("id-ID", o).format(d);
  const now = new Date();
  const monday = new Date(now);
  monday.setDate(now.getDate() - ((now.getDay() + 6) % 7));
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  const short = { day: "numeric", month: "short" };
  return {
    today: fmt(now, { weekday: "long", day: "numeric", month: "short", year: "numeric" }),
    week: `${fmt(monday, short)} sampai ${fmt(sunday, short)}`,
    month: fmt(now, { month: "long", year: "numeric" }),
  };
}

export default function LaporanScreen() {
  const dates = volumeDates();
  const [status, setStatus] = useState("loading"); // loading | error | done
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [actions, setActions] = useState(null); // null = memuat, false = gagal
  const [team, setTeam] = useState(null); // null = tidak punya team (atau gagal): bagiannya tetap tersembunyi

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
    getReportTeam()
      .then(setTeam)
      .catch(() => setTeam(null));
  }, []);

  useEffect(() => {
    getReportActionItems()
      .then(setActions)
      .catch(() => setActions(false));
  }, []);

  // item di sini milik suatu rapat (meeting_id + index) dan menandainya selesai harus memperbarui hitungan halaman ini juga
  // (daftar terbuka, pembagian terbuka/selesai per penanggung jawab). Optimistis, dikembalikan kalau gagal
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
      // Dikembalikan dengan menaruhnya di akhir daftar - urutan asli yang persis
      // tidak sepadan dilacak untuk jalur gagal yang seharusnya jarang.
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
                <StatCard value={stats.meetings.today} label="Hari Ini" delta={dates.today} />
                <StatCard value={stats.meetings.this_week} label="Minggu Ini" delta={dates.week} />
                <StatCard value={stats.meetings.this_month} label="Bulan Ini" delta={dates.month} />
                <StatCard value={stats.meetings.total} label="Total" delta="Semua waktu" />
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
                <View style={styles.chartBody}>
                  {/* semua platform, walau 0, supaya kartunya tidak pernah berisi satu batang kesepian */}
                  <HorizontalBarChart
                    labelWidth={90}
                    fill
                    data={Object.keys(PLATFORM_LABELS).map((platform) => ({
                      label: PLATFORM_LABELS[platform],
                      value: stats.platform_counts[platform] || 0,
                      color: PLATFORM_COLORS[platform],
                    }))}
                  />
                </View>
              </View>
            </View>
          </View>
        )}

        {team && (
          <>
            <Text style={styles.sectionLabel}>Pemakaian Team ({team.team.name})</Text>
            <View style={styles.columns}>
              <View style={styles.column}>
                <View style={[styles.statRow, { flexGrow: 1 }]}>
                  <StatCard value={team.totals.meetings} label="Rapat Team" delta="Semua anggota" />
                  <StatCard value={team.totals.this_month} label="Bulan Ini" delta={dates.month} />
                  <StatCard value={team.totals.shared} label="Dibagikan ke Team" />
                  <StatCard value={`${(team.totals.minutes / 60).toFixed(1)} jam`} label="Total Durasi Rekaman" />
                </View>
              </View>
              <View style={styles.column}>
                <View style={styles.chartCard}>
                  <Text style={styles.chartTitle}>Pemakaian per Anggota</Text>
                  <View style={styles.chartBody}>
                  {team.members.map((m) => {
                    const max = Math.max(1, ...team.members.map((x) => x.meetings));
                    return (
                      <View key={m.id} style={{ gap: 4 }}>
                        <View style={styles.memberRow}>
                          <Text style={styles.memberName} numberOfLines={1}>
                            {m.name}
                            {m.role === "admin" ? " (Admin)" : ""}
                          </Text>
                          <Text style={styles.memberMeta}>
                            {m.meetings} rapat, {m.this_month} bulan ini
                          </Text>
                        </View>
                        <View style={styles.memberTrack}>
                          <View style={{ width: `${Math.max(2, (m.meetings / max) * 100)}%`, height: 6, backgroundColor: colors.gold }} />
                        </View>
                      </View>
                    );
                  })}
                  </View>
                </View>
              </View>
            </View>
          </>
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
                  <View style={styles.chartBody}>
                    <HorizontalBarChart
                      data={actions.by_assignee.slice(0, 8).map((r) => ({
                        label: r.assignee,
                        value: r.open + r.done,
                        color: r.open > 0 ? colors.goldDeep : colors.success,
                      }))}
                    />
                  </View>
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

  // stretch + kartu terakhir yang tumbuh: kedua kolom berakhir di garis yang sama, tidak ada celah kosong di bawah yang lebih pendek
  columns: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, alignItems: "stretch" },
  column: { flex: 1, minWidth: 380, gap: spacing.md },
  openRow: { flexDirection: "row", gap: 8, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.border },
  openTask: { ...type.small, fontSize: 13.5, color: colors.ink, lineHeight: 18 },
  openMeta: { ...type.small, color: colors.inkFaint },
  sectionLabel: { ...type.eyebrow, color: colors.inkFaint, marginTop: spacing.md },
  statRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, alignContent: "stretch" },

  chartCard: {
    flexGrow: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.md,
    ...shadow.card,
  },
  // Grafiknya di tengah kartu yang diregangkan sampai setinggi tetangganya.
  chartBody: { flex: 1, justifyContent: "space-evenly", gap: spacing.md },
  chartTitle: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },

  stateBox: { alignItems: "center", gap: spacing.sm, padding: spacing.xl },
  memberRow: { flexDirection: "row", justifyContent: "space-between", gap: spacing.sm },
  memberName: { ...type.small, fontWeight: "600", color: colors.ink, flex: 1 },
  memberMeta: { ...type.small, color: colors.inkSoft, fontVariant: ["tabular-nums"], flexShrink: 1, textAlign: "right" },
  memberTrack: { height: 6, borderRadius: 3, backgroundColor: colors.border, overflow: "hidden" },
  stateText: { ...type.body, color: colors.inkSoft, textAlign: "center" },
});
