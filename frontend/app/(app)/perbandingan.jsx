import { Feather } from "@expo/vector-icons";
import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { getMeeting, listMeetings } from "@/lib/api";
import { formatMeetingDate, PLATFORM_LABEL } from "@/lib/format";

// Only meetings with a real summary are worth comparing.
function comparable(meetings) {
  return meetings.filter((m) => m.status === "completed" && m.recording);
}

// Raw <select> (web-only app, same reasoning as the file input in
// rapat/upload.jsx and the drag-and-drop div there) — a native dropdown
// handles long lists and keyboard input for free, no custom component needed.
// appearance:"none" drops the browser's own (inconsistently-styled) arrow so
// a Feather chevron matching the rest of the app can sit on top instead.
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
          backgroundColor: colors.surfaceSunken,
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
      <Feather
        name="chevron-down"
        size={16}
        color={colors.inkFaint}
        style={{ position: "absolute", right: 12, pointerEvents: "none" }}
      />
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

  const pickable = allMeetings.filter((m) => m.id !== excludeId);
  const meeting = state.data;
  const summary = meeting?.summary;
  const items = summary?.action_items || [];
  const doneCount = items.filter((a) => a.done).length;

  return (
    <View style={styles.col}>
      <Text style={styles.colLabel}>{label}</Text>
      <MeetingPicker meetings={pickable} value={meetingId} onChange={onPick} placeholder="Pilih rapat..." />

      {state.status === "loading" && (
        <View style={styles.stateBox}>
          <ActivityIndicator color={colors.gold} />
        </View>
      )}
      {state.status === "error" && <Text style={styles.stateText}>Gagal memuat rapat ini.</Text>}

      {meeting && (
        <>
          <View style={styles.metaCard}>
            <Text style={styles.meetingTitle} numberOfLines={2}>
              {meeting.title}
            </Text>
            <Text style={styles.meetingMeta}>
              {PLATFORM_LABEL[meeting.platform] || meeting.platform} · {meeting.date}, {meeting.time}
            </Text>
            <View style={styles.statRow}>
              <View style={styles.statCell}>
                <Text style={styles.statValue}>{meeting.duration_minutes != null ? `${meeting.duration_minutes} mnt` : "—"}</Text>
                <Text style={styles.statLabel}>Durasi</Text>
              </View>
              <View style={styles.statCell}>
                <Text style={styles.statValue}>{summary?.key_decisions?.length || 0}</Text>
                <Text style={styles.statLabel}>Keputusan</Text>
              </View>
              <View style={styles.statCell}>
                <Text style={styles.statValue}>
                  {doneCount}/{items.length}
                </Text>
                <Text style={styles.statLabel}>Action Item Selesai</Text>
              </View>
            </View>
          </View>

          {!summary ? (
            <Text style={styles.stateText}>Rapat ini belum punya ringkasan.</Text>
          ) : (
            <>
              <View style={styles.block}>
                <Text style={styles.blockLabel}>RINGKASAN</Text>
                <Text style={styles.blockText}>{summary.executive_summary}</Text>
              </View>

              <View style={styles.block}>
                <Text style={styles.blockLabel}>KEPUTUSAN UTAMA ({summary.key_decisions?.length || 0})</Text>
                {(summary.key_decisions || []).map((d, i) => (
                  <View key={i} style={styles.bulletRow}>
                    <Feather name="check-circle" size={13} color={colors.success} style={{ marginTop: 3 }} />
                    <Text style={[styles.blockText, { flex: 1 }]}>{d}</Text>
                  </View>
                ))}
              </View>

              <View style={styles.block}>
                <Text style={styles.blockLabel}>TOPIK DIBAHAS ({summary.topics_discussed?.length || 0})</Text>
                <View style={styles.chipRow}>
                  {(summary.topics_discussed || []).map((t, i) => (
                    <View key={i} style={styles.chip}>
                      <Text style={styles.chipLabel}>{t}</Text>
                    </View>
                  ))}
                </View>
              </View>

              <View style={styles.block}>
                <Text style={styles.blockLabel}>
                  ACTION ITEM ({doneCount}/{items.length} selesai)
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
            </>
          )}
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
        <Text style={styles.title}>Perbandingan Rapat</Text>
        <Text style={styles.description}>Bandingkan ringkasan, keputusan, dan action item dua rapat secara berdampingan.</Text>

        {status === "loading" && (
          <View style={styles.stateBox}>
            <ActivityIndicator color={colors.gold} />
          </View>
        )}
        {status === "error" && <Text style={styles.stateText}>Gagal memuat daftar rapat.</Text>}
        {notEnough && <Text style={styles.stateText}>Butuh minimal 2 rapat yang sudah selesai untuk dibandingkan.</Text>}

        {status === "done" && meetings.length >= 2 && (
          <View style={styles.grid}>
            <MeetingColumn meetings={meetings} allMeetings={meetings} meetingId={leftId} excludeId={rightId} onPick={setLeftId} label="RAPAT A" />
            <MeetingColumn meetings={meetings} allMeetings={meetings} meetingId={rightId} excludeId={leftId} onPick={setRightId} label="RAPAT B" />
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

  title: { ...type.h1, fontSize: 24, color: colors.ink },
  description: { ...type.body, color: colors.inkSoft, marginTop: 2, marginBottom: spacing.sm },

  stateBox: { alignItems: "center", gap: spacing.sm, padding: spacing.xl },
  stateText: { ...type.body, color: colors.inkSoft },

  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, alignItems: "flex-start" },
  col: { flex: 1, minWidth: 420, gap: spacing.md },
  colLabel: { ...type.eyebrow, color: colors.inkFaint },

  metaCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: 4,
    ...shadow.card,
  },
  meetingTitle: { ...type.h2, color: colors.ink },
  meetingMeta: { ...type.small, color: colors.inkFaint },
  statRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  statCell: {
    flex: 1,
    alignItems: "center",
    backgroundColor: colors.surfaceSunken,
    borderRadius: radius.sm,
    paddingVertical: spacing.sm,
  },
  statValue: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },
  statLabel: { ...type.small, color: colors.inkFaint, marginTop: 2, textAlign: "center" },

  block: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: 8,
    ...shadow.card,
  },
  blockLabel: { ...type.eyebrow, color: colors.inkFaint },
  blockText: { ...type.small, fontSize: 13.5, lineHeight: 19, color: colors.ink },
  bulletRow: { flexDirection: "row", gap: 8 },
  done: { color: colors.inkFaint, textDecorationLine: "line-through" },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: { backgroundColor: colors.surfaceSunken, borderRadius: radius.pill, paddingVertical: 4, paddingHorizontal: 10 },
  chipLabel: { ...type.small, color: colors.inkSoft },
});
