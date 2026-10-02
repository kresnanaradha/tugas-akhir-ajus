import { Feather } from "@expo/vector-icons";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { StatusPill } from "@/components/StatusPill";
import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { getComparisonExportUrl, getMeeting, listMeetings } from "@/lib/api";
import { formatMeetingDate, PLATFORM_LABEL } from "@/lib/format";

// Same accent per platform as components/MeetingRow.jsx, here as the colored
// top edge of each meeting's header card.
const PLATFORM_ACCENT = {
  google_meet: colors.success,
  zoom: colors.info,
  upload: colors.gold,
};

// Only meetings with a real summary are worth comparing.
function comparable(meetings) {
  return meetings.filter((m) => m.status === "completed" && m.recording);
}

// Raw <select> (web-only app, same reasoning as the file input in
// rapat/upload.jsx) — a native dropdown handles long lists and keyboard input
// for free. appearance:"none" drops the browser's own inconsistently-styled
// arrow so a Feather chevron matching the rest of the app sits on top instead.
function MeetingPicker({ meetings, value, onChange, placeholder }) {
  return (
    <View style={{ position: "relative", justifyContent: "center" }}>
      <select
        value={value || ""}
        onChange={(e) => onChange(e.target.value || null)}
        style={{
          width: "100%",
          padding: "11px 36px 11px 12px",
          borderRadius: radius.sm,
          border: `1px solid ${colors.border}`,
          backgroundColor: colors.surface,
          color: colors.ink,
          fontSize: 14.5,
          outline: "none",
          appearance: "none",
          WebkitAppearance: "none",
          cursor: "pointer",
        }}
      >
        <option value="">{placeholder}</option>
        {meetings.map((m) => (
          <option key={m.id} value={m.id} disabled={m.id === value}>
            {m.title} · {m.date}, {m.time}
          </option>
        ))}
      </select>
      <Feather name="chevron-down" size={16} color={colors.inkFaint} style={{ position: "absolute", right: 12, pointerEvents: "none" }} />
    </View>
  );
}

function SectionCard({ icon, title, count, children }) {
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

function MeetingColumn({ meetingId, allMeetings, excludeId, onPick, label }) {
  const [state, setState] = useState({ status: "idle", data: null });

  useEffect(() => {
    if (!meetingId) {
      setState({ status: "idle", data: null });
      return;
    }
    let cancelled = false;
    setState({ status: "loading", data: null });
    getMeeting(meetingId)
      .then((data) => !cancelled && setState({ status: "done", data }))
      .catch(() => !cancelled && setState({ status: "error", data: null }));
    return () => {
      cancelled = true;
    };
  }, [meetingId]);

  const picker = (
    <>
      <Text style={styles.colLabel}>{label}</Text>
      <MeetingPicker
        meetings={allMeetings.filter((m) => m.id !== excludeId)}
        value={meetingId}
        onChange={onPick}
        placeholder="Pilih rapat..."
      />
    </>
  );

  if (state.status !== "done") {
    return (
      <View style={styles.col}>
        {picker}
        {state.status === "loading" && (
          <View style={styles.stateBox}>
            <ActivityIndicator color={colors.gold} />
          </View>
        )}
        {state.status === "error" && <Text style={styles.stateText}>Gagal memuat rapat ini.</Text>}
      </View>
    );
  }

  const meeting = state.data;
  const summary = meeting.summary;
  const { date, time } = formatMeetingDate(meeting.created_at);
  const decisions = summary?.key_decisions || [];
  const topics = summary?.topics_discussed || [];
  const items = summary?.action_items || [];

  return (
    <View style={styles.col}>
      {picker}
      <View style={[styles.headCard, { borderTopColor: PLATFORM_ACCENT[meeting.platform] || colors.border }]}>
        <View style={styles.headTop}>
          <StatusPill status={meeting.status} />
          <Text style={styles.platformLabel}>{PLATFORM_LABEL[meeting.platform] || meeting.platform}</Text>
        </View>
        <Text style={styles.meetingTitle} numberOfLines={2}>
          {meeting.title}
        </Text>
        <View style={styles.metaRow}>
          <View style={styles.metaItem}>
            <Feather name="calendar" size={12} color={colors.inkFaint} />
            <Text style={styles.metaText}>
              {date}, {time}
            </Text>
          </View>
          {meeting.duration_minutes != null && (
            <View style={styles.metaItem}>
              <Feather name="clock" size={12} color={colors.inkFaint} />
              <Text style={styles.metaText}>{meeting.duration_minutes} mnt</Text>
            </View>
          )}
          {meeting.estimated_participants != null && (
            <View style={styles.metaItem}>
              <Feather name="users" size={12} color={colors.inkFaint} />
              <Text style={styles.metaText}>~{meeting.estimated_participants} peserta</Text>
            </View>
          )}
        </View>
        <Pressable style={styles.detailButton} onPress={() => router.push(`/rapat/${meeting.id}`)}>
          <Text style={styles.detailButtonLabel}>Lihat Detail</Text>
          <Feather name="chevron-right" size={13} color={colors.inkSoft} />
        </Pressable>
      </View>

      {!summary ? (
        <Text style={styles.stateText}>Rapat ini belum punya ringkasan.</Text>
      ) : (
        <>
          <SectionCard icon="zap" title="Ringkasan AI">
            <Text style={styles.bodyText}>{summary.executive_summary}</Text>
          </SectionCard>

          <SectionCard icon="hash" title="Topik Dibahas" count={topics.length}>
            <View style={styles.chipRow}>
              {topics.map((t, i) => (
                <View key={i} style={styles.chip}>
                  <Text style={styles.chipLabel}>{t}</Text>
                </View>
              ))}
              {topics.length === 0 && <Text style={styles.mutedText}>Tidak ada topik tercatat.</Text>}
            </View>
          </SectionCard>

          <SectionCard icon="check-circle" title="Keputusan" count={decisions.length}>
            {decisions.map((d, i) => (
              <View key={i} style={styles.bulletRow}>
                <Feather name="check-circle" size={13} color={colors.success} style={{ marginTop: 3 }} />
                <Text style={[styles.bodyText, { flex: 1 }]}>{d}</Text>
              </View>
            ))}
            {decisions.length === 0 && <Text style={styles.mutedText}>Tidak ada keputusan tercatat.</Text>}
          </SectionCard>

          <SectionCard icon="list" title="Action Items" count={items.length}>
            {items.map((a, i) => (
              <View key={i} style={styles.bulletRow}>
                <Feather
                  name={a.done ? "check-square" : "square"}
                  size={14}
                  color={a.done ? colors.success : colors.inkFaint}
                  style={{ marginTop: 2 }}
                />
                <Text style={[styles.bodyText, { flex: 1 }, a.done && styles.done]}>
                  {a.task}
                  {a.assignee || a.due ? (
                    <Text style={styles.mutedText}>{`  — ${[a.assignee, a.due].filter(Boolean).join(" · ")}`}</Text>
                  ) : null}
                </Text>
              </View>
            ))}
            {items.length === 0 && <Text style={styles.mutedText}>Tidak ada action item.</Text>}
          </SectionCard>
        </>
      )}
    </View>
  );
}

export default function PerbandinganScreen() {
  const [status, setStatus] = useState("loading");
  const [meetings, setMeetings] = useState([]);
  const [leftId, setLeftId] = useState(null);
  const [rightId, setRightId] = useState(null);

  useEffect(() => {
    listMeetings()
      .then((data) => {
        const rows = comparable(data.map((m) => ({ ...m, ...formatMeetingDate(m.created_at) })));
        setMeetings(rows);
        setLeftId(rows[0]?.id ?? null);
        setRightId(rows[1]?.id ?? null);
        setStatus("done");
      })
      .catch(() => setStatus("error"));
  }, []);

  const notEnough = status === "done" && meetings.length < 2;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.title}>Perbandingan Rapat</Text>
            <Text style={styles.description}>Bandingkan ringkasan, keputusan, dan insight dua rapat secara berdampingan.</Text>
          </View>
          {leftId && rightId && (
            <Pressable style={styles.primaryButton} onPress={() => window.open(getComparisonExportUrl(leftId, rightId), "_blank")}>
              <Feather name="download" size={14} color={colors.ink} />
              <Text style={styles.primaryButtonLabel}>Export PDF</Text>
            </Pressable>
          )}
        </View>

        {status === "loading" && (
          <View style={styles.stateBox}>
            <ActivityIndicator color={colors.gold} />
          </View>
        )}
        {status === "error" && <Text style={styles.stateText}>Gagal memuat daftar rapat.</Text>}
        {notEnough && <Text style={styles.stateText}>Butuh minimal 2 rapat yang sudah selesai untuk dibandingkan.</Text>}

        {status === "done" && meetings.length >= 2 && (
          <View style={styles.grid}>
            <MeetingColumn allMeetings={meetings} meetingId={leftId} excludeId={rightId} onPick={setLeftId} label="RAPAT A" />
            <MeetingColumn allMeetings={meetings} meetingId={rightId} excludeId={leftId} onPick={setRightId} label="RAPAT B" />
          </View>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { alignItems: "center", padding: spacing.lg },
  content: { gap: spacing.md, maxWidth: 1400, width: "100%" },

  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: spacing.lg },
  title: { ...type.h1, fontSize: 24, color: colors.ink },
  description: { ...type.body, color: colors.inkSoft, marginTop: 2 },
  primaryButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    backgroundColor: colors.gold,
    paddingVertical: 8,
    paddingHorizontal: spacing.md,
    borderRadius: radius.sm,
    ...shadow.card,
  },
  primaryButtonLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },

  stateBox: { alignItems: "center", gap: spacing.sm, padding: spacing.xl },
  stateText: { ...type.body, color: colors.inkSoft },
  mutedText: { ...type.small, color: colors.inkFaint },

  colLabel: { ...type.eyebrow, color: colors.inkFaint },

  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, alignItems: "flex-start" },
  col: { flex: 1, minWidth: 320, gap: spacing.md },

  headCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderTopWidth: 3,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
    ...shadow.card,
  },
  headTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  platformLabel: { ...type.small, color: colors.inkFaint },
  meetingTitle: { ...type.h2, color: colors.ink },
  metaRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  metaItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  metaText: { ...type.small, color: colors.inkFaint },
  detailButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 4,
    backgroundColor: colors.surfaceSunken,
    borderRadius: radius.sm,
    paddingVertical: 9,
    marginTop: spacing.xs,
  },
  detailButtonLabel: { ...type.small, fontWeight: "600", color: colors.inkSoft },

  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
    ...shadow.card,
  },
  cardHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  cardIcon: {
    width: 24,
    height: 24,
    borderRadius: radius.sm,
    backgroundColor: colors.goldSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  cardTitle: { ...type.bodyMedium, fontWeight: "700", color: colors.ink, flex: 1 },
  countBadge: { backgroundColor: colors.surfaceSunken, borderRadius: radius.pill, paddingVertical: 1, paddingHorizontal: 8 },
  countBadgeLabel: { ...type.small, fontWeight: "700", color: colors.inkSoft },
  bodyText: { ...type.small, fontSize: 13.5, lineHeight: 19, color: colors.inkSoft },
  bulletRow: { flexDirection: "row", gap: 8 },
  done: { color: colors.inkFaint, textDecorationLine: "line-through" },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: { backgroundColor: colors.surfaceSunken, borderRadius: radius.pill, paddingVertical: 4, paddingHorizontal: 10 },
  chipLabel: { ...type.small, color: colors.inkSoft },
});
