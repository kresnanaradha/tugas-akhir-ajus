import { Feather } from "@expo/vector-icons";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { StatusPill } from "@/components/StatusPill";
import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { getComparisonAnalysis, getComparisonExportUrl, getMeeting, listMeetings } from "@/lib/api";
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

// Loads one meeting's detail; the page keeps both so the two sides can be laid
// out row by row (each section of A level with the same section of B).
function useMeeting(meetingId) {
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

  return state;
}

function HeadColumn({ state, meetingId, allMeetings, excludeId, onPick, label }) {
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
  const { date, time } = formatMeetingDate(meeting.created_at);

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
    </View>
  );
}

// One comparison row per section, in the order the advisor asked for: topics
// first, the (truncated) summary after. Each renders the card of ONE meeting.
const SECTIONS = [
  {
    icon: "hash",
    title: "Topik Dibahas",
    count: (s) => (s.topics_discussed || []).length,
    body: (s) => {
      const topics = s.topics_discussed || [];
      return (
        <View style={styles.chipRow}>
          {topics.map((t, i) => (
            <View key={i} style={styles.chip}>
              <Text style={styles.chipLabel}>{t}</Text>
            </View>
          ))}
          {topics.length === 0 && <Text style={styles.mutedText}>Tidak ada topik tercatat.</Text>}
        </View>
      );
    },
  },
  {
    icon: "align-left",
    title: "Ringkasan",
    body: (s, meeting) => (
      <>
        <Text style={styles.bodyText} numberOfLines={5}>
          {s.short_summary || s.executive_summary}
        </Text>
        <Pressable onPress={() => router.push(`/rapat/${meeting.id}`)}>
          <Text style={styles.moreLink}>Baca selengkapnya</Text>
        </Pressable>
      </>
    ),
  },
  {
    icon: "check-circle",
    title: "Keputusan",
    count: (s) => (s.key_decisions || []).length,
    body: (s) => {
      const decisions = s.key_decisions || [];
      return (
        <>
          {decisions.map((d, i) => (
            <View key={i} style={styles.bulletRow}>
              <Feather name="check-circle" size={13} color={colors.success} style={{ marginTop: 3 }} />
              <Text style={[styles.bodyText, { flex: 1 }]}>{d}</Text>
            </View>
          ))}
          {decisions.length === 0 && <Text style={styles.mutedText}>Tidak ada keputusan tercatat.</Text>}
        </>
      );
    },
  },
  {
    icon: "list",
    title: "Action Items",
    count: (s) => (s.action_items || []).length,
    body: (s) => {
      const items = s.action_items || [];
      return (
        <>
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
        </>
      );
    },
  },
];

// A and B cards side by side; the row stretches so both cards are the same height.
function CompareRow({ section, left, right }) {
  const cell = (state) => {
    const meeting = state.data;
    const summary = meeting?.summary;
    if (state.status !== "done") return <View style={styles.col} />;
    return (
      <View style={styles.col}>
        <SectionCard icon={section.icon} title={section.title} count={summary && section.count ? section.count(summary) : null}>
          {summary ? section.body(summary, meeting) : <Text style={styles.mutedText}>Rapat ini belum punya ringkasan.</Text>}
        </SectionCard>
      </View>
    );
  };
  return (
    <View style={styles.grid}>
      {cell(left)}
      {cell(right)}
    </View>
  );
}

const ANALYSIS_BLOCKS = [
  ["similarities", "Kesamaan", "link", colors.success],
  ["differences", "Perbedaan", "shuffle", colors.info],
  ["progress", "Perkembangan dari Rapat A ke B", "trending-up", colors.goldDeep],
];

function AnalysisCard({ leftId, rightId }) {
  const [state, setState] = useState({ status: "loading", data: null, error: "" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", data: null, error: "" });
    getComparisonAnalysis(leftId, rightId)
      .then((data) => !cancelled && setState({ status: "done", data, error: "" }))
      .catch((e) => !cancelled && setState({ status: "error", data: null, error: e.message || "" }));
    return () => {
      cancelled = true;
    };
  }, [leftId, rightId]);

  const data = state.data;
  return (
    <SectionCard icon="cpu" title="Perbandingan AI">
      {state.status === "loading" && (
        <View style={styles.aiLoading}>
          <ActivityIndicator color={colors.gold} />
          <Text style={styles.mutedText}>AI sedang membandingkan kedua rapat...</Text>
        </View>
      )}
      {state.status === "error" && <Text style={styles.stateText}>{state.error || "Perbandingan AI gagal dibuat."}</Text>}
      {data && (
        <>
          {!!(data.about_a || data.about_b) && (
            <View style={{ gap: spacing.xs }}>
              {!!data.about_a && <Text style={styles.bodyText}>{data.about_a}</Text>}
              {!!data.about_b && <Text style={styles.bodyText}>{data.about_b}</Text>}
            </View>
          )}
          {ANALYSIS_BLOCKS.map(([key, title, icon, color]) =>
            data[key]?.length ? (
              <View key={key} style={{ gap: spacing.xs }}>
                <Text style={styles.aiHeading}>{title}</Text>
                {data[key].map((line, i) => (
                  <View key={i} style={styles.bulletRow}>
                    <Feather name={icon} size={13} color={color} style={{ marginTop: 3 }} />
                    <Text style={[styles.bodyText, { flex: 1 }]}>{line}</Text>
                  </View>
                ))}
              </View>
            ) : null
          )}
          {!!data.conclusion && (
            <View style={styles.conclusionBox}>
              <Text style={styles.aiHeading}>Kesimpulan</Text>
              <Text style={styles.bodyText}>{data.conclusion}</Text>
            </View>
          )}
        </>
      )}
    </SectionCard>
  );
}

export default function PerbandinganScreen() {
  const [status, setStatus] = useState("loading");
  const [meetings, setMeetings] = useState([]);
  const [leftId, setLeftId] = useState(null);
  const [rightId, setRightId] = useState(null);
  const left = useMeeting(leftId);
  const right = useMeeting(rightId);

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

        {status === "done" && leftId && rightId && <AnalysisCard leftId={leftId} rightId={rightId} />}

        {status === "done" && meetings.length >= 2 && (
          <>
            <View style={styles.grid}>
              <HeadColumn state={left} allMeetings={meetings} meetingId={leftId} excludeId={rightId} onPick={setLeftId} label="RAPAT A" />
              <HeadColumn state={right} allMeetings={meetings} meetingId={rightId} excludeId={leftId} onPick={setRightId} label="RAPAT B" />
            </View>
            {SECTIONS.map((section) => (
              <CompareRow key={section.title} section={section} left={left} right={right} />
            ))}
          </>
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

  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
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
    flexGrow: 1,
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
  moreLink: { ...type.small, fontWeight: "600", color: colors.goldDeep },
  aiLoading: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  aiHeading: { ...type.eyebrow, color: colors.inkFaint },
  conclusionBox: { backgroundColor: colors.surfaceSunken, borderRadius: radius.sm, padding: spacing.md, gap: spacing.xs },
  bodyText: { ...type.small, fontSize: 13.5, lineHeight: 19, color: colors.inkSoft },
  bulletRow: { flexDirection: "row", gap: 8 },
  done: { color: colors.inkFaint, textDecorationLine: "line-through" },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: { backgroundColor: colors.surfaceSunken, borderRadius: radius.pill, paddingVertical: 4, paddingHorizontal: 10 },
  chipLabel: { ...type.small, color: colors.inkSoft },
});
