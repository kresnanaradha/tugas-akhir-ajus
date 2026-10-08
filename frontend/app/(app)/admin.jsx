import { Feather } from "@expo/vector-icons";
import { Redirect } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { getAdminExportUrl, getAdminStats } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { BarChart } from "@/components/BarChart";
import { HorizontalBarChart } from "@/components/HorizontalBarChart";
import { StatCard } from "@/components/StatCard";
import { UserManagement } from "@/components/UserManagement";

// Same fixed categorical order already used for speaker badges elsewhere in
// this app (see rapat/[id].jsx's SPEAKER_PALETTE) — reused here instead of
// picking new colors, so "categorical series" reads consistently across the
// whole product rather than each chart inventing its own order.
const PLAN_COLORS = { free: colors.inkFaint, pro: colors.info, team: colors.success };
const PLAN_LABELS = { free: "Free", pro: "Pro", team: "Team" };

function formatIDR(n) {
  return new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 }).format(n || 0);
}

function formatBytes(bytes) {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = -1;
  do {
    value /= 1024;
    unit++;
  } while (value >= 1024 && unit < units.length - 1);
  return `${value.toFixed(1)} ${units[unit]}`;
}

export default function AdminScreen() {
  const { user } = useAuth();
  const [status, setStatus] = useState("loading"); // loading | error | done
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (user?.role !== "super_admin") return;
    getAdminStats()
      .then((data) => {
        setStats(data);
        setStatus("done");
      })
      .catch((e) => {
        setError(e.message || "Gagal memuat statistik");
        setStatus("error");
      });
  }, [user]);

  // Regular users (and even the render-before-user-loads moment) never see
  // this page's content — bounced straight back rather than shown an
  // empty/error shell. The backend independently enforces this too
  // (403 on /admin/stats for a non-super_admin session), this is just so
  // the UI doesn't flash a page a regular user isn't meant to reach.
  if (user && user.role !== "super_admin") {
    return <Redirect href="/dashboard" />;
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <View style={styles.headerRow}>
          <View>
            <Text style={styles.eyebrow}>SUPER ADMIN</Text>
            <Text style={styles.title}>Dashboard</Text>
            <Text style={styles.description}>Statistik penggunaan, biaya, dan pendapatan seluruh sistem Notulis.</Text>
          </View>
          <Pressable style={styles.exportButton} onPress={() => window.open(getAdminExportUrl(), "_blank")}>
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
          <>
            <View style={styles.columns}>
            <View style={styles.column}>
            <Text style={styles.sectionLabel}>Volume Rapat</Text>
            <View style={styles.statRow}>
              <StatCard value={stats.meetings.today} label="Rapat Hari Ini" />
              <StatCard value={stats.meetings.this_week} label="Rapat Minggu Ini" />
              <StatCard value={stats.meetings.this_month} label="Rapat Bulan Ini" />
              <StatCard value={stats.meetings.total} label="Total Rapat Sepanjang Waktu" />
            </View>
            <View style={styles.chartCard}>
              <Text style={styles.chartTitle}>Rapat per Hari (14 Hari Terakhir)</Text>
              <BarChart data={stats.meetings_daily.map((d) => ({ date: d.date, value: d.count }))} />
            </View>

            </View>
            <View style={styles.column}>
            <Text style={styles.sectionLabel}>Bisnis</Text>
            <View style={styles.statRow}>
              <StatCard value={formatIDR(stats.mrr_idr)} label="Pendapatan Berjalan (MRR)" />
              <StatCard
                value={Object.values(stats.plan_counts).reduce((a, b) => a + b, 0)}
                label="Subscriber Aktif"
                delta={Object.entries(stats.plan_counts)
                  .map(([plan, n]) => `${n} ${plan}`)
                  .join(", ") || "belum ada"}
              />
              <StatCard value={stats.users_total} label="Total Pengguna Terdaftar" />
              <StatCard
                value={`${Math.round((stats.meetings.completed / (stats.meetings.total || 1)) * 100)}%`}
                label="Tingkat Keberhasilan Rapat"
                delta={`${stats.meetings.failed} gagal`}
                deltaColor={colors.danger}
              />
            </View>
            <View style={styles.chartCard}>
              <Text style={styles.chartTitle}>Distribusi Plan Pengguna</Text>
              <HorizontalBarChart
                data={["free", "pro", "team"].map((plan) => ({
                  label: PLAN_LABELS[plan],
                  value:
                    plan === "free"
                      ? Math.max(0, stats.users_total - Object.values(stats.plan_counts).reduce((a, b) => a + b, 0))
                      : stats.plan_counts[plan] || 0,
                  color: PLAN_COLORS[plan],
                }))}
              />
            </View>

            </View>
            </View>

            <Text style={styles.sectionLabel}>Biaya & Penyimpanan</Text>
            <View style={styles.statRow}>
              <StatCard
                value={`$${stats.openai_cost.total_usd.toFixed(4)}`}
                label="Biaya OpenAI API"
                delta={stats.openai_cost.since ? `sejak ${new Date(stats.openai_cost.since).toLocaleDateString("id-ID")}` : "belum ada data"}
              />
              <StatCard value={stats.openai_cost.call_count} label="Jumlah Panggilan API" />
              <StatCard value={formatBytes(stats.storage_bytes)} label="Penyimpanan R2 Terpakai" />
            </View>
          </>
        )}

        <Text style={styles.sectionLabel}>Manajemen Pengguna</Text>
        <UserManagement currentUserId={user?.id} />
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
