import { Feather } from "@expo/vector-icons";
import { Link, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { getMeeting, listMeetings } from "@/lib/api";
import { formatMeetingDate, PLATFORM_LABEL } from "@/lib/format";
import { MeetingRow } from "@/components/MeetingRow";
import { StatusPill } from "@/components/StatusPill";
import { useAuth } from "@/lib/auth-context";

const LIVE = ["joining", "recording", "stopping", "processing"];
const FILTERS = [
  { key: "all", label: "Semua", test: () => true },
  { key: "google_meet", label: "Google Meet", test: (m) => m.platform === "google_meet" },
  { key: "zoom", label: "Zoom", test: (m) => m.platform === "zoom" },
  { key: "upload", label: "Upload", test: (m) => m.platform === "upload" },
  { key: "failed", label: "Gagal", test: (m) => m.status === "failed" },
];

// Right half of the page: a read-only preview of the selected meeting (summary,
// key decisions, action items), so the list can be skimmed without opening
// every meeting. Fetches the full record when the selection changes.
function MeetingPreview({ meeting }) {
  const [state, setState] = useState({ status: "idle", data: null });

  useEffect(() => {
    if (!meeting) return;
    if (meeting.status === "failed" || LIVE.includes(meeting.status)) {
      setState({ status: "idle", data: null });
      return;
    }
    let cancelled = false;
    setState({ status: "loading", data: null });
    getMeeting(meeting.id)
      .then((data) => !cancelled && setState({ status: "done", data }))
      .catch(() => !cancelled && setState({ status: "error", data: null }));
    return () => {
      cancelled = true;
    };
  }, [meeting?.id, meeting?.status]);

  if (!meeting) {
    return (
      <View style={styles.previewEmpty}>
        <Feather name="mouse-pointer" size={20} color={colors.inkFaint} />
        <Text style={styles.stateText}>Pilih satu rapat di kiri untuk melihat ringkasannya di sini.</Text>
      </View>
    );
  }

  const summary = state.data?.summary;
  const items = summary?.action_items || [];
  return (
    <View style={styles.preview}>
      <View style={styles.previewHead}>
        <View style={{ flex: 1, gap: 4 }}>
          <Text style={styles.previewTitle} numberOfLines={2}>
            {meeting.title}
          </Text>
          <Text style={styles.previewMeta}>
            {PLATFORM_LABEL[meeting.platform] || meeting.platform} · {meeting.date}, {meeting.time}
            {meeting.duration_minutes != null ? ` · ${meeting.duration_minutes} mnt` : ""}
          </Text>
        </View>
        <StatusPill status={meeting.status} />
      </View>

      <ScrollView style={styles.previewBody} contentContainerStyle={{ gap: spacing.md }}>
        {state.status === "loading" && <ActivityIndicator color={colors.gold} />}
        {state.status === "error" && <Text style={styles.stateText}>Gagal memuat ringkasan.</Text>}
        {state.status === "idle" && (
          <Text style={styles.stateText}>
            {meeting.status === "failed" ? "Rapat ini gagal diproses." : "Rapat masih berjalan, ringkasan belum tersedia."}
          </Text>
        )}
        {state.status === "done" && !summary && <Text style={styles.stateText}>Belum ada ringkasan untuk rapat ini.</Text>}

        {summary && (
          <>
            <View style={styles.block}>
              <Text style={styles.blockLabel}>RINGKASAN</Text>
              <Text style={styles.blockText}>{summary.executive_summary}</Text>
            </View>
            {summary.key_decisions?.length > 0 && (
              <View style={styles.block}>
                <Text style={styles.blockLabel}>KEPUTUSAN UTAMA</Text>
                {summary.key_decisions.map((d, i) => (
                  <View key={i} style={styles.bulletRow}>
                    <Feather name="check-circle" size={13} color={colors.success} style={{ marginTop: 3 }} />
                    <Text style={[styles.blockText, { flex: 1 }]}>{d}</Text>
                  </View>
                ))}
              </View>
            )}
            {items.length > 0 && (
              <View style={styles.block}>
                <Text style={styles.blockLabel}>
                  ACTION ITEM ({items.filter((a) => a.done).length}/{items.length} selesai)
                </Text>
                {items.map((a, i) => (
                  <View key={i} style={styles.bulletRow}>
                    <Feather
                      name={a.done ? "check-square" : "square"}
                      size={13}
                      color={a.done ? colors.success : colors.inkFaint}
                      style={{ marginTop: 3 }}
                    />
                    <Text style={[styles.blockText, { flex: 1 }, a.done && styles.done]}>
                      {a.task}
                      {a.assignee || a.due ? `  (${[a.assignee, a.due].filter(Boolean).join(" · ")})` : ""}
                    </Text>
                  </View>
                ))}
              </View>
            )}
          </>
        )}
      </ScrollView>

      <Link href={`/rapat/${meeting.id}`} asChild>
        <Pressable style={styles.openButton}>
          <Text style={styles.openButtonLabel}>Buka Detail</Text>
          <Feather name="arrow-right" size={14} color={colors.ink} />
        </Pressable>
      </Link>
    </View>
  );
}

export default function RapatScreen() {
  const { q } = useLocalSearchParams();
  const { user } = useAuth();
  const [status, setStatus] = useState("loading"); // loading | error | done
  const [meetings, setMeetings] = useState([]);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  // Pre-filled from the TopBar's search box (?q=...) but editable here too.
  const [searchQuery, setSearchQuery] = useState(q ? String(q) : "");
  const [selectedId, setSelectedId] = useState(null);

  useEffect(() => {
    listMeetings()
      .then((data) => {
        const rows = data.map((m) => ({
          ...m,
          ...formatMeetingDate(m.created_at),
          isFromTeammate: !!m.user_id && m.user_id !== user?.id,
        }));
        setMeetings(rows);
        setSelectedId(rows[0]?.id ?? null);
        setStatus("done");
      })
      .catch((e) => {
        setError(e.message || "Gagal memuat daftar rapat");
        setStatus("error");
      });
  }, []);

  const test = FILTERS.find((f) => f.key === filter).test;
  const q2 = searchQuery.trim().toLowerCase();
  const visible = meetings.filter(test).filter((m) => !q2 || m.title.toLowerCase().includes(q2));
  const selected = meetings.find((m) => m.id === selectedId) || null;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
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

        <View style={styles.split}>
          <View style={styles.listCol}>
            <View style={styles.searchBox}>
              <Feather name="search" size={14} color={colors.inkFaint} />
              <TextInput
                style={styles.searchInput}
                placeholder="Cari judul rapat..."
                placeholderTextColor={colors.inkFaint}
                value={searchQuery}
                onChangeText={setSearchQuery}
              />
              {!!searchQuery && (
                <Pressable onPress={() => setSearchQuery("")} hitSlop={6}>
                  <Feather name="x" size={14} color={colors.inkFaint} />
                </Pressable>
              )}
            </View>

            <View style={styles.filterRow}>
              {FILTERS.map((f) => (
                <Pressable
                  key={f.key}
                  style={[styles.chip, filter === f.key && styles.chipActive]}
                  onPress={() => setFilter(f.key)}
                >
                  <Text style={[styles.chipLabel, filter === f.key && styles.chipLabelActive]}>
                    {f.label}
                    {status === "done" ? ` ${meetings.filter(f.test).length}` : ""}
                  </Text>
                </Pressable>
              ))}
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

              {status === "done" && visible.length === 0 && (
                <View style={styles.stateBox}>
                  <Feather name="inbox" size={20} color={colors.inkFaint} />
                  <Text style={styles.stateText}>
                    {meetings.length === 0
                      ? 'Belum ada rapat yang direkam. Mulai dari "Rapat Baru" atau "Upload" di dashboard.'
                      : "Tidak ada rapat untuk filter ini."}
                  </Text>
                </View>
              )}

              {status === "done" &&
                visible.map((meeting) => (
                  <MeetingRow
                    key={meeting.id}
                    meeting={meeting}
                    selected={meeting.id === selectedId}
                    onSelect={() => setSelectedId(meeting.id)}
                  />
                ))}
            </View>
          </View>

          <View style={styles.previewCol}>
            <MeetingPreview meeting={selected} />
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

  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: spacing.lg },
  titleRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  title: { ...type.h1, fontSize: 24, color: colors.ink },
  countBadge: {
    backgroundColor: colors.goldSoft,
    borderRadius: radius.pill,
    paddingVertical: 3,
    paddingHorizontal: 10,
  },
  countBadgeLabel: { ...type.small, fontWeight: "700", color: colors.goldDeep },
  description: { ...type.body, color: colors.inkSoft, marginTop: 2 },

  newButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    backgroundColor: colors.gold,
    paddingVertical: 8,
    paddingHorizontal: spacing.md,
    borderRadius: radius.sm,
    ...shadow.card,
  },
  newButtonLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },

  split: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, alignItems: "flex-start" },
  listCol: { flex: 1.15, minWidth: 420, gap: spacing.sm },
  previewCol: { flex: 1, minWidth: 340 },

  searchBox: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    height: 38,
  },
  searchInput: { ...type.body, color: colors.ink, flex: 1, outlineStyle: "none" },
  filterRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: {
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  chipActive: { backgroundColor: colors.gold, borderColor: colors.gold },
  chipLabel: { ...type.small, fontWeight: "600", color: colors.inkSoft },
  chipLabelActive: { color: colors.ink },

  panel: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: "hidden",
    ...shadow.card,
  },
  stateBox: { alignItems: "center", gap: spacing.sm, padding: spacing.xl },
  stateText: { ...type.body, color: colors.inkSoft, textAlign: "center" },

  preview: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.md,
    ...shadow.card,
  },
  previewEmpty: {
    alignItems: "center",
    gap: spacing.sm,
    padding: spacing.xl,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: "dashed",
    borderColor: colors.border,
  },
  previewHead: { flexDirection: "row", alignItems: "flex-start", gap: spacing.md },
  previewTitle: { ...type.h2, color: colors.ink },
  previewMeta: { ...type.small, color: colors.inkFaint },
  previewBody: { maxHeight: 460 },
  block: { gap: 6 },
  blockLabel: { ...type.eyebrow, color: colors.inkFaint },
  blockText: { ...type.small, fontSize: 13.5, lineHeight: 19, color: colors.ink },
  bulletRow: { flexDirection: "row", gap: 8 },
  done: { color: colors.inkFaint, textDecorationLine: "line-through" },
  openButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    backgroundColor: colors.gold,
    paddingVertical: 8,
    borderRadius: radius.sm,
  },
  openButtonLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },
});
