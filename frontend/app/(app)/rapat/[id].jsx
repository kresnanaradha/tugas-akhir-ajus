import { Feather } from "@expo/vector-icons";
import { Link, useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { deleteMeeting, getJobStatus, getMeeting, getRecordingUrl, replaceActionItems, setKnowledgeBase, stopJob, toggleActionItem, updateTranscript } from "@/lib/api";
import { formatMeetingDate, PLATFORM_LABEL } from "@/lib/format";
import { StatusPill } from "@/components/StatusPill";

// Cycles through existing theme colors rather than introducing new ones —
// consistent color per speaker label, not a real identity (diarization only
// gives us numbered speakers, not names). Hashes the whole label (not just
// a trailing "_00" digit) so a renamed/merged speaker ("Kresna") still gets
// a stable color, and two labels that get merged into the same name
// automatically end up the same color too.
const SPEAKER_PALETTE = [colors.info, colors.success, colors.goldDeep, colors.danger];
function speakerColor(speaker) {
  if (!speaker) return SPEAKER_PALETTE[0];
  let hash = 0;
  for (let i = 0; i < speaker.length; i++) hash = (hash * 31 + speaker.charCodeAt(i)) >>> 0;
  return SPEAKER_PALETTE[hash % SPEAKER_PALETTE.length];
}

// transcribe.py writes one "[SPEAKER_NN] text" line per utterance — parsed
// back into rows for the editable view so each speaker gets its own styled
// line instead of one giant plain-text blob. Falls back to a speaker-less
// row for anything that doesn't match (blank lines, older formats).
const LINE_PATTERN = /^\[(.+?)\]\s?(.*)$/;
function parseTranscriptLines(text) {
  return (text || "").split("\n").map((line) => {
    const match = LINE_PATTERN.exec(line);
    return match ? { speaker: match[1], text: match[2] } : { speaker: null, text: line };
  });
}
// Per line, resolves to whichever rename applies: a line-only override (for
// when diarization mis-attributed just that one line — a different person
// said it, not actually the same speaker) beats a global rename of the raw
// speaker id (e.g. SPEAKER_00 -> "Kresna" everywhere), which beats the raw
// id itself. null for a speaker-less line.
function resolveLineSpeakers(lines, speakerNames, lineOverrides) {
  return lines.map((l, i) => (l.speaker ? lineOverrides[i] || speakerNames[l.speaker] || l.speaker : null));
}
function joinTranscriptLines(lines, lineSpeakers) {
  return lines.map((l, i) => (lineSpeakers[i] ? `[${lineSpeakers[i]}] ${l.text}` : l.text)).join("\n");
}

// The editor always starts from the raw transcript, but a save also writes the
// chosen names and edited text into segments.json (same line order). Rebuild
// the editor state from that so saved names/edits are still there after a
// reload: per raw speaker id the most common saved name wins (global rename),
// and any line that differs from it becomes a per-line override.
function buildEditorState(meeting) {
  let lines = parseTranscriptLines(meeting.transcript);
  const names = {};
  const overrides = {};
  const segs = meeting.segments;
  if (segs && segs.length === lines.length) {
    const counts = {};
    lines.forEach((l, i) => {
      if (!l.speaker) return;
      const n = segs[i].speaker || l.speaker;
      counts[l.speaker] = counts[l.speaker] || {};
      counts[l.speaker][n] = (counts[l.speaker][n] || 0) + 1;
    });
    for (const raw of Object.keys(counts)) {
      const [best] = Object.entries(counts[raw]).sort((a, b) => b[1] - a[1])[0];
      if (best !== raw) names[raw] = best;
    }
    lines.forEach((l, i) => {
      if (!l.speaker) return;
      const n = segs[i].speaker || l.speaker;
      if (n !== (names[l.speaker] || l.speaker)) overrides[i] = n;
    });
    lines = lines.map((l, i) => ({ ...l, text: segs[i].text ?? l.text }));
  }
  return { lines, names, overrides };
}

function SpeakerBadge({ speaker }) {
  const color = speakerColor(speaker);
  return (
    <View style={[styles.speakerBadge, { backgroundColor: `${color}22` }]}>
      <Text style={[styles.speakerBadgeLabel, { color }]}>{speaker}</Text>
    </View>
  );
}

// One row of the "Nama Pembicara" panel: renames a diarization id
// (SPEAKER_00) everywhere. Keeps its own draft and only commits on blur/enter,
// so lines don't change (and the field doesn't snap back to the raw id when
// emptied) while the user is still typing. Empty commit = back to the raw id.
// Raw <textarea> (web-only app) that grows to fit its text. RN's multiline
// TextInput always reserves at least two rows, which left an empty gap under
// every one-line transcript row.
function LineTextarea({ value, onChange, onFocus }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);
  return (
    <textarea
      ref={ref}
      rows={1}
      value={value}
      onFocus={onFocus}
      onChange={(e) => onChange(e.target.value)}
      style={{
        width: "100%",
        boxSizing: "border-box",
        border: "none",
        outline: "none",
        resize: "none",
        overflow: "hidden",
        background: "transparent",
        padding: 0,
        margin: 0,
        display: "block",
        fontFamily: 'System, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
        fontSize: 14,
        lineHeight: "20px",
        color: colors.ink,
      }}
    />
  );
}

function SpeakerNameRow({ raw, name, onCommit }) {
  const [draft, setDraft] = useState(name);
  useEffect(() => setDraft(name), [name]);
  const commit = () => onCommit(draft.trim());
  const color = speakerColor(raw);
  return (
    <View style={styles.nameCell}>
      <View style={styles.nameCellLabel}>
        <View style={[styles.mergeMenuDot, { backgroundColor: color }]} />
        <Text style={[styles.nameCellRaw, { color }]}>{raw}</Text>
      </View>
      <TextInput
        style={[styles.nameInput, !!name && styles.nameInputFilled]}
        value={draft}
        placeholder="Nama asli"
        placeholderTextColor={colors.inkFaint}
        onChangeText={setDraft}
        onBlur={commit}
        onSubmitEditing={commit}
      />
    </View>
  );
}

// Per-line badge: click to move just this line to another speaker (for when
// diarization put one sentence under the wrong person). Renaming a whole
// speaker happens in the panel above instead.
function LineSpeakerBadge({ raw, value, overridden, options, open, onToggle, onPick, onReset }) {
  const color = speakerColor(overridden ? value : raw);
  return (
    <View style={styles.speakerBadgeWrap}>
      <Pressable onPress={onToggle} style={[styles.speakerBadge, { backgroundColor: `${color}22` }]}>
        <Text style={[styles.speakerBadgeLabel, { color }]}>{value}</Text>
        <Feather name="chevron-down" size={11} color={color} />
      </Pressable>
      {open && (
        <View style={styles.mergeMenu}>
          <Text style={styles.mergeMenuLabel}>Pindahkan baris ini ke:</Text>
          {options.map((label) => (
            <Pressable key={label} style={styles.mergeMenuItem} onPress={() => onPick(label)}>
              <View style={[styles.mergeMenuDot, { backgroundColor: speakerColor(label) }]} />
              <Text style={styles.mergeMenuItemLabel}>{label}</Text>
            </Pressable>
          ))}
          {overridden && (
            <Pressable style={styles.mergeMenuItem} onPress={onReset}>
              <Feather name="rotate-ccw" size={11} color={colors.inkSoft} />
              <Text style={styles.mergeMenuItemLabel}>Kembalikan ke pembicara asli</Text>
            </Pressable>
          )}
        </View>
      )}
    </View>
  );
}

function formatBytes(bytes) {
  if (bytes == null) return null;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatElapsed(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

const LIVE_STATUSES = ["joining", "recording", "stopping", "processing"];
const STEPS = [
  { key: "joining", label: "Bergabung" },
  { key: "recording", label: "Merekam" },
  { key: "processing", label: "Memproses" },
];
const STEP_INDEX = { joining: 0, recording: 1, stopping: 1, processing: 2 };

const TABS = [
  { key: "ringkasan", label: "Ringkasan AI", icon: "zap" },
  { key: "transkrip", label: "Transkrip", icon: "file-text" },
  { key: "edit", label: "Edit Transkrip", icon: "edit-3" },
];

function PulsingDot() {
  const opacity = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.3, duration: 700, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 1, duration: 700, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [opacity]);
  return <Animated.View style={[styles.pulseDot, { opacity }]} />;
}

export default function MeetingDetailScreen() {
  const { id } = useLocalSearchParams();
  const [screenStatus, setScreenStatus] = useState("loading"); // loading | error | done
  const [meeting, setMeeting] = useState(null);
  const [error, setError] = useState("");
  const [currentTime, setCurrentTime] = useState(0);
  const videoRef = useRef(null);
  const [activeTab, setActiveTab] = useState("ringkasan");

  // Live-job state (only relevant while meeting.status is one of LIVE_STATUSES)
  const [liveStatus, setLiveStatus] = useState(null); // null once finished/not live
  const [elapsed, setElapsed] = useState(0);
  const [liveError, setLiveError] = useState("");
  const pollTimer = useRef(null);
  const pollFailures = useRef(0);

  // Transcript editor (Edit Transkrip tab) — left is the raw transcript,
  // editable per speaker line (parsed from the "[SPEAKER_NN] text" lines
  // transcribe.py writes) rather than one plain-text blob; right is the
  // AI-corrected version, read-only, shown as a reference to correct against.
  const [editedLines, setEditedLines] = useState([]);
  // { SPEAKER_00: "Kresna", ... } — renames a speaker id everywhere at once,
  // keyed by the original id so the badge color (which derives from the id)
  // stays stable even after renaming.
  const [speakerNames, setSpeakerNames] = useState({});
  // { <line index>: "Diva", ... } — overrides just one line, for when
  // diarization mis-attributed that single line to the wrong speaker
  // cluster rather than the whole cluster actually being a different person.
  const [lineOverrides, setLineOverrides] = useState({});
  // Which line's "gabung ke speaker lain" pick-list is open — only one at
  // a time, since it's rendered inline right under that line's badge.
  const [mergeOpenIndex, setMergeOpenIndex] = useState(null);
  // Which raw transcript line is currently focused for editing — the "Saran
  // Perbaikan AI" column only shows that one line's AI-corrected version
  // (by the same index into fixed_transcript's lines) instead of the whole
  // thing, so the suggestion right next to what's being typed is obvious
  // instead of buried in a long parallel scroll.
  const [focusedLineIndex, setFocusedLineIndex] = useState(null);
  const [savingTranscript, setSavingTranscript] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [kbSaving, setKbSaving] = useState(false);
  const [kbError, setKbError] = useState("");
  const [savedNotice, setSavedNotice] = useState(false);
  // Edits (names, moved lines, text) not yet saved: the summary only changes on save.
  const [dirty, setDirty] = useState(false);
  const router = useRouter();
  // Action item editor: which item is being edited (index, "new", or null) + its draft.
  const [editingItem, setEditingItem] = useState(null);
  const [itemDraft, setItemDraft] = useState({ task: "", assignee: "", due: "" });
  const [itemSaving, setItemSaving] = useState(false);
  const [itemError, setItemError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  // Edit tab: which raw-transcript line the video is currently on. Lines map to
  // segments by index (same assumption the save sync already relies on), so
  // only trust it when both have the same length.
  const [playing, setPlaying] = useState(false);
  const editorScrollRef = useRef(null);
  const lineEls = useRef({});
  const activeLine =
    meeting?.segments && meeting.segments.length === editedLines.length
      ? meeting.segments.findIndex((seg) => seg.start != null && currentTime >= seg.start && currentTime < seg.end)
      : -1;
  // Follow the video only while it plays, so it never fights the user typing.
  useEffect(() => {
    // Web-only app: measure the row's DOM node against the scroll box directly.
    const box = editorScrollRef.current?.getScrollableNode?.();
    const row = lineEls.current[activeLine];
    if (playing && box && row) {
      const top = row.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop - 40;
      box.scrollTop = Math.max(0, top);
    }
  }, [activeLine, playing]);

  useEffect(() => () => clearTimeout(pollTimer.current), []);

  useEffect(() => {
    getMeeting(id)
      .then((data) => {
        setMeeting(data);
        const editor = buildEditorState(data);
        setEditedLines(editor.lines);
        setSpeakerNames(editor.names);
        setLineOverrides(editor.overrides);
        setScreenStatus("done");
        if (LIVE_STATUSES.includes(data.status)) {
          setLiveStatus(data.status);
          poll(id);
        }
      })
      .catch((e) => {
        setError(e.message || "Gagal memuat detail rapat");
        setScreenStatus("error");
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // A rejected fetch here means the request itself couldn't complete (a
  // network blip, Docker being briefly slow to respond, CORS hiccup, etc)
  // -- it says nothing about whether the job succeeded or failed. A real
  // job failure comes back as a normal 200 with {status: "failed"} in the
  // body, handled separately below. Treating a transient fetch error as
  // "failed" used to kill the polling loop outright (no retry scheduled),
  // permanently freezing the UI at whatever liveStatus it last had -- e.g.
  // a Zoom join whose next poll would've shown "recording" instead sat
  // stuck on "joining" for 30+ seconds until the user manually left and
  // reopened the page. Retrying (with a cap so a genuinely dead backend
  // doesn't poll forever) fixes both that and the "shows failed" glitch.
  const MAX_CONSECUTIVE_POLL_FAILURES = 10;

  // GET /jobs/<id> only knows jobs held in that server process's memory. A 404
  // there does not mean the job failed: the server may have restarted, or the
  // job may be running in a different worker container, or was started outside
  // the API. The meetings table still tracks the real status, so fall back to
  // polling that until it stops being a live status.
  function pollMeeting() {
    getMeeting(id)
      .then((fresh) => {
        if (LIVE_STATUSES.includes(fresh.status)) {
          setLiveStatus(fresh.status);
          pollTimer.current = setTimeout(pollMeeting, 3000);
          return;
        }
        setMeeting(fresh);
        const editor = buildEditorState(fresh);
        setEditedLines(editor.lines);
        setSpeakerNames(editor.names);
        setLineOverrides(editor.overrides);
        setLiveStatus(null);
      })
      .catch(() => {
        pollTimer.current = setTimeout(pollMeeting, 3000);
      });
  }

  function poll(jobId) {
    getJobStatus(jobId)
      .then((data) => {
        pollFailures.current = 0;
        setLiveStatus(data.status);
        if (data.elapsed_seconds != null) setElapsed(data.elapsed_seconds);
        if (data.status === "done") {
          // Re-fetch the canonical, now-finished record instead of trying to
          // reconstruct it from the job response — same data a page reload
          // would show, and picks up segments/file info the job response
          // never carried.
          getMeeting(id).then((fresh) => {
            setMeeting(fresh);
            const editor = buildEditorState(fresh);
            setEditedLines(editor.lines);
            setSpeakerNames(editor.names);
            setLineOverrides(editor.overrides);
            setLiveStatus(null);
          });
        } else if (data.status === "failed") {
          setLiveError(data.error || "Terjadi kesalahan");
        } else {
          pollTimer.current = setTimeout(() => poll(jobId), 1000);
        }
      })
      .catch((e) => {
        if (e.status === 404) {
          pollMeeting();
          return;
        }
        pollFailures.current += 1;
        if (pollFailures.current >= MAX_CONSECUTIVE_POLL_FAILURES) {
          setLiveError(e.message || "Gagal memuat status rekaman");
          setLiveStatus("failed");
          return;
        }
        pollTimer.current = setTimeout(() => poll(jobId), 1000);
      });
  }

  function handleStop() {
    // Fire-and-forget — the next poll() tick reflects the real status
    // regardless of whether this particular call succeeds. Still needs a
    // .catch(): if the job already moved past "recording" (e.g. a double
    // click, or it finished right before this landed), the backend 404s and
    // an uncaught rejection here crashes the whole page in dev.
    stopJob(id).catch(() => {});
  }

  function seekTo(seconds) {
    if (videoRef.current) videoRef.current.currentTime = seconds;
  }

  async function handleSaveTranscript() {
    setSavingTranscript(true);
    setSaveError("");
    setSavedNotice(false);
    try {
      // Re-runs the summary against whatever the user just approved/edited —
      // the meeting's summary afterward reflects that corrected transcript,
      // not the model's first pass.
      const lineSpeakers = resolveLineSpeakers(editedLines, speakerNames, lineOverrides);
      const result = await updateTranscript(
        id,
        joinTranscriptLines(editedLines, lineSpeakers),
        lineSpeakers,
        editedLines.map((l) => l.text)
      );
      setMeeting((m) => ({
        ...m,
        fixed_transcript: result.fixed_transcript,
        segments: result.segments ?? m.segments,
        summary: result.summary ?? null,
        summary_error: result.summary_error,
      }));
      setSavedNotice(true);
      setDirty(false);
    } catch (e) {
      setSaveError(e.message || "Gagal menyimpan transkrip");
    } finally {
      setSavingTranscript(false);
    }
  }

  function handleToggleActionItem(index) {
    // Optimistic, and the local state stays the source of truth: the request
    // carries the wanted value and its response is ignored (it may predate a
    // later click), so rapid successive checks can't erase each other. Only
    // this one item is reverted if the save fails.
    const done = !meeting.summary.action_items[index].done;
    const setDone = (value) =>
      setMeeting((m) => ({
        ...m,
        summary: {
          ...m.summary,
          action_items: m.summary.action_items.map((item, i) => (i === index ? { ...item, done: value } : item)),
        },
      }));
    setDone(done);
    toggleActionItem(id, index, done).catch(() => setDone(!done));
  }

  function startEditItem(index) {
    const item = index === "new" ? {} : meeting.summary.action_items[index];
    setItemDraft({ task: item.task || "", assignee: item.assignee || "", due: item.due || "" });
    setItemError("");
    setEditingItem(index);
  }

  async function saveItems(items) {
    setItemSaving(true);
    setItemError("");
    try {
      const summary = await replaceActionItems(id, items);
      setMeeting((m) => ({ ...m, summary }));
      setEditingItem(null);
    } catch (e) {
      setItemError(e.message || "Gagal menyimpan action item");
    } finally {
      setItemSaving(false);
    }
  }

  function handleSaveItem() {
    if (!itemDraft.task.trim()) {
      setItemError("Isi tugas tidak boleh kosong");
      return;
    }
    const items = [...(meeting.summary.action_items || [])];
    if (editingItem === "new") items.push({ ...itemDraft, done: false });
    else items[editingItem] = { ...items[editingItem], ...itemDraft };
    saveItems(items);
  }

  function handleRemoveItem(index) {
    saveItems(meeting.summary.action_items.filter((_, i) => i !== index));
  }

  async function handleDeleteMeeting() {
    setDeleting(true);
    setDeleteError("");
    try {
      await deleteMeeting(id);
      router.replace("/rapat");
    } catch (e) {
      setDeleteError(e.message || "Gagal menghapus rapat");
      setDeleting(false);
    }
  }

  function renderItemForm(index) {
    return (
      <View key={index} style={styles.itemForm}>
        <TextInput
          style={styles.itemInput}
          value={itemDraft.task}
          onChangeText={(task) => setItemDraft((d) => ({ ...d, task }))}
          placeholder="Tugas"
          placeholderTextColor={colors.inkFaint}
          multiline
        />
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          <TextInput
            style={[styles.itemInput, { flex: 1 }]}
            value={itemDraft.assignee}
            onChangeText={(assignee) => setItemDraft((d) => ({ ...d, assignee }))}
            placeholder="Penanggung jawab"
            placeholderTextColor={colors.inkFaint}
          />
          <TextInput
            style={[styles.itemInput, { flex: 1 }]}
            value={itemDraft.due}
            onChangeText={(due) => setItemDraft((d) => ({ ...d, due }))}
            placeholder="Tenggat"
            placeholderTextColor={colors.inkFaint}
          />
        </View>
        {!!itemError && <Text style={styles.errorText}>{itemError}</Text>}
        <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center" }}>
          <Pressable style={[styles.smallButton, styles.smallButtonPrimary]} onPress={handleSaveItem} disabled={itemSaving}>
            <Text style={styles.smallButtonLabel}>{itemSaving ? "Menyimpan..." : "Simpan"}</Text>
          </Pressable>
          <Pressable style={styles.smallButton} onPress={() => setEditingItem(null)} disabled={itemSaving}>
            <Text style={styles.smallButtonLabel}>Batal</Text>
          </Pressable>
          {index !== "new" && (
            <Pressable style={{ marginLeft: "auto" }} onPress={() => handleRemoveItem(index)} disabled={itemSaving}>
              <Text style={[styles.smallButtonLabel, { color: colors.danger }]}>Hapus</Text>
            </Pressable>
          )}
        </View>
      </View>
    );
  }

  function handleToggleKb() {
    const enabled = !meeting.in_kb;
    setKbSaving(true);
    setKbError("");
    setKnowledgeBase(id, enabled)
      .then(() => setMeeting((m) => ({ ...m, in_kb: enabled })))
      .catch((e) => setKbError(e.message || "Gagal memperbarui Knowledge Base"))
      .finally(() => setKbSaving(false));
  }

  const isLive = liveStatus && liveStatus !== "failed";
  const isLiveFailed = liveStatus === "failed";
  const stepIndex = STEP_INDEX[liveStatus] ?? 0;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <Link href="/rapat" style={styles.backLink}>
          <Feather name="chevron-left" size={14} color={colors.inkSoft} /> Kembali ke Daftar Rapat
        </Link>

        {screenStatus === "loading" && (
          <View style={styles.stateBox}>
            <ActivityIndicator color={colors.gold} />
          </View>
        )}

        {screenStatus === "error" && (
          <View style={styles.stateBox}>
            <Feather name="alert-circle" size={20} color={colors.danger} />
            <Text style={styles.stateText}>{error}</Text>
          </View>
        )}

        {screenStatus === "done" && meeting && (
          <>
            {/* Header */}
            <View style={styles.headerCard}>
              <View style={styles.badgeRow}>
                <StatusPill status={isLive || isLiveFailed ? liveStatus : meeting.status} />
                <View style={styles.platformBadge}>
                  <Feather name="video" size={12} color={colors.inkSoft} />
                  <Text style={styles.platformBadgeLabel}>{PLATFORM_LABEL[meeting.platform] || meeting.platform}</Text>
                </View>
                {!isLive && !confirmDelete && (
                  <Pressable style={[styles.smallButton, { marginLeft: "auto" }]} onPress={() => setConfirmDelete(true)}>
                    <Feather name="trash-2" size={12} color={colors.danger} />
                    <Text style={[styles.smallButtonLabel, { color: colors.danger }]}>Hapus Rapat</Text>
                  </Pressable>
                )}
                {confirmDelete && (
                  <View style={{ marginLeft: "auto", flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                    {!!deleteError && <Text style={styles.errorText}>{deleteError}</Text>}
                    <Text style={styles.actionItemMeta}>Hapus permanen beserta rekaman dan transkrip?</Text>
                    <Pressable style={[styles.smallButton, styles.smallButtonDanger]} onPress={handleDeleteMeeting} disabled={deleting}>
                      <Text style={[styles.smallButtonLabel, { color: "#fff" }]}>{deleting ? "Menghapus..." : "Ya, hapus"}</Text>
                    </Pressable>
                    <Pressable style={styles.smallButton} onPress={() => setConfirmDelete(false)} disabled={deleting}>
                      <Text style={styles.smallButtonLabel}>Batal</Text>
                    </Pressable>
                  </View>
                )}
              </View>
              <Text style={styles.title}>{meeting.title}</Text>
              <View style={styles.metaRow}>
                <Feather name="calendar" size={13} color={colors.inkFaint} />
                <Text style={styles.metaText}>
                  {formatMeetingDate(meeting.created_at).date}, {formatMeetingDate(meeting.created_at).time}
                </Text>
                {meeting.duration_minutes != null && (
                  <>
                    <Feather name="clock" size={13} color={colors.inkFaint} style={styles.metaIconGap} />
                    <Text style={styles.metaText}>{meeting.duration_minutes} menit</Text>
                  </>
                )}
                {meeting.estimated_participants != null && (
                  <>
                    <Feather name="users" size={13} color={colors.inkFaint} style={styles.metaIconGap} />
                    <Text style={styles.metaText}>~{meeting.estimated_participants} peserta (perkiraan)</Text>
                  </>
                )}
              </View>
            </View>

            {/* Live view — bot still joining/recording/processing */}
            {isLive && (
              <View style={styles.liveCard}>
                <View style={styles.stepper}>
                  {STEPS.map((step, i) => (
                    <View key={step.key} style={styles.stepItemWrap}>
                      <View style={styles.stepItem}>
                        <View style={[styles.stepDot, i <= stepIndex && styles.stepDotActive]} />
                        <Text style={[styles.stepLabel, i === stepIndex && styles.stepLabelActive]}>{step.label}</Text>
                      </View>
                      {i < STEPS.length - 1 && <View style={[styles.stepLine, i < stepIndex && styles.stepLineActive]} />}
                    </View>
                  ))}
                </View>

                {liveStatus === "recording" || liveStatus === "stopping" ? (
                  <View style={styles.liveCenter}>
                    <View style={styles.liveStatusRow}>
                      <PulsingDot />
                      <Text style={styles.liveStatusText}>
                        {liveStatus === "stopping" ? "Menghentikan rekaman..." : "Sedang merekam"}
                      </Text>
                    </View>
                    <Text style={styles.liveTimer}>{formatElapsed(elapsed)}</Text>
                  </View>
                ) : (
                  <View style={styles.liveCenter}>
                    <ActivityIndicator color={colors.gold} size="large" />
                    <Text style={styles.liveStatusText}>
                      {liveStatus === "joining" ? "Bot sedang bergabung ke rapat..." : "Memproses transkripsi & ringkasan..."}
                    </Text>
                  </View>
                )}

                {liveStatus === "recording" && (
                  <Pressable style={styles.stopButton} onPress={handleStop}>
                    <Feather name="square" size={13} color={colors.white} />
                    <Text style={styles.stopButtonLabel}>Stop Rekam</Text>
                  </Pressable>
                )}

                <View style={styles.liveInfoBox}>
                  <Feather name="info" size={13} color={colors.goldDeep} />
                  <Text style={styles.liveInfoText}>
                    Anda bisa tinggalkan halaman ini, proses tetap berjalan di server. Cek lagi lewat daftar Rapat kapan
                    saja.
                  </Text>
                </View>
              </View>
            )}

            {/* Live job failed before producing anything */}
            {isLiveFailed && (
              <View style={styles.liveCard}>
                <View style={styles.liveFailedRow}>
                  <Feather name="alert-circle" size={20} color={colors.danger} />
                  <Text style={styles.errorText}>{liveError || "Bot gagal bergabung ke rapat."}</Text>
                </View>
              </View>
            )}

            {/* Finished — tabbed Ringkasan AI / Transkrip / Rekaman */}
            {!isLive && !isLiveFailed && (
              <>
                <View style={styles.tabBar}>
                  {TABS.map((tab) => {
                    const active = activeTab === tab.key;
                    return (
                      <Pressable
                        key={tab.key}
                        style={[styles.tabButton, active && styles.tabButtonActive]}
                        onPress={() => setActiveTab(tab.key)}
                      >
                        <Feather name={tab.icon} size={13} color={active ? colors.ink : colors.inkFaint} />
                        <Text style={[styles.tabLabel, active && styles.tabLabelActive]}>{tab.label}</Text>
                      </Pressable>
                    );
                  })}
                </View>

                {activeTab === "ringkasan" &&
                  (meeting.summary ? (
                    <View style={styles.section}>
                      <View style={styles.summaryCard}>
                        <View style={styles.summaryCardHeader}>
                          <View style={styles.iconWrap}>
                            <Feather name="zap" size={16} color={colors.goldDeep} />
                          </View>
                          <Text style={[styles.summaryCardLabel, { flex: 1 }]}>Executive Summary</Text>
                          <Pressable
                            style={[styles.kbButton, meeting.in_kb && styles.kbButtonOn]}
                            onPress={handleToggleKb}
                            disabled={kbSaving}
                          >
                            <Feather name={meeting.in_kb ? "check" : "plus"} size={13} color={colors.ink} />
                            <Text style={styles.kbButtonLabel}>
                              {kbSaving ? "Menyimpan..." : meeting.in_kb ? "Ada di Knowledge Base" : "Simpan ke Knowledge Base"}
                            </Text>
                          </Pressable>
                        </View>
                        {!!kbError && <Text style={styles.errorText}>{kbError}</Text>}
                        <Text style={styles.summaryText}>{meeting.summary.executive_summary}</Text>
                      </View>

                      <View style={styles.twoCol}>
                        <View style={styles.colCard}>
                          <Text style={styles.colTitle}>Keputusan Utama</Text>
                          {meeting.summary.key_decisions?.map((d, i) => (
                            <View key={i} style={styles.decisionRow}>
                              <Feather name="check-circle" size={14} color={colors.success} />
                              <Text style={styles.decisionText}>{d}</Text>
                            </View>
                          ))}
                        </View>
                        <View style={styles.colCard}>
                          <Text style={styles.colTitle}>Topik Dibahas</Text>
                          {meeting.summary.topics_discussed?.map((t, i) => (
                            <View key={i} style={styles.topicRow}>
                              <Text style={styles.topicIndex}>{i + 1}</Text>
                              <Text style={styles.topicText}>{t}</Text>
                            </View>
                          ))}
                        </View>
                      </View>

                      <View style={styles.actionItemsCard}>
                        <View style={styles.actionItemsHeader}>
                          <Text style={[styles.colTitle, { flex: 1 }]}>Action Items</Text>
                          {editingItem !== "new" && (
                            <Pressable style={styles.smallButton} onPress={() => startEditItem("new")}>
                              <Feather name="plus" size={12} color={colors.ink} />
                              <Text style={styles.smallButtonLabel}>Tambah</Text>
                            </Pressable>
                          )}
                        </View>
                        {!meeting.summary.action_items?.length && editingItem !== "new" && (
                          <Text style={styles.actionItemMeta}>Belum ada action item.</Text>
                        )}
                        {meeting.summary.action_items?.map((item, i) =>
                          editingItem === i ? (
                            renderItemForm(i)
                          ) : (
                            <View key={i} style={styles.actionItemRow}>
                              <Pressable onPress={() => handleToggleActionItem(i)} hitSlop={6}>
                                <Feather
                                  name={item.done ? "check-square" : "square"}
                                  size={15}
                                  color={item.done ? colors.success : colors.inkFaint}
                                  style={{ marginTop: 2 }}
                                />
                              </Pressable>
                              <View style={{ flex: 1 }}>
                                <Text style={[styles.actionItemTask, item.done && styles.actionItemTaskDone]}>
                                  {item.task}
                                </Text>
                                {(item.assignee || item.due) && (
                                  <Text style={styles.actionItemMeta}>
                                    {[item.assignee, item.due].filter(Boolean).join(" · ")}
                                  </Text>
                                )}
                              </View>
                              <Pressable onPress={() => startEditItem(i)} hitSlop={6}>
                                <Feather name="edit-2" size={13} color={colors.inkFaint} style={{ marginTop: 3 }} />
                              </Pressable>
                            </View>
                          )
                        )}
                        {editingItem === "new" && renderItemForm("new")}
                      </View>
                    </View>
                  ) : (
                    <View style={styles.section}>
                      <Text style={styles.errorText}>Ringkasan gagal: {meeting.summary_error || "tidak diketahui"}.</Text>
                    </View>
                  ))}

                {activeTab === "transkrip" && (
                  <View style={styles.section}>
                    <View style={styles.mediaGrid}>
                      <View style={styles.videoCol}>
                        {/* Raw <video> (not an RN component) — native browser controls give
                            accurate play/pause/seek/duration for free, no custom waveform UI
                            needed. This app targets web only. */}
                        <video
                          ref={videoRef}
                          controls
                          style={{ width: "100%", borderRadius: radius.md, backgroundColor: "#000", aspectRatio: "16/9" }}
                          src={getRecordingUrl(meeting.id)}
                          onTimeUpdate={(e) => setCurrentTime(e.target.currentTime)}
                        />
                        <View style={styles.fileInfoRow}>
                          <Text style={styles.fileInfoText}>
                            {meeting.file_extension && `Format: ${meeting.file_extension.toUpperCase()}`}
                            {meeting.file_extension && meeting.file_size_bytes != null && " · "}
                            {formatBytes(meeting.file_size_bytes) && `Ukuran: ${formatBytes(meeting.file_size_bytes)}`}
                          </Text>
                          {/* Raw <a download> — real file download, this is a real deployed
                              app (not a sandboxed artifact preview) so it works normally. */}
                          <a href={getRecordingUrl(meeting.id)} download style={{ textDecorationLine: "none" }}>
                            <View style={styles.downloadBtn}>
                              <Feather name="download" size={13} color={colors.ink} />
                              <Text style={styles.downloadLabel}>Unduh</Text>
                            </View>
                          </a>
                        </View>
                      </View>

                      <View style={styles.transcriptCol}>
                        {meeting.segments ? (
                          <ScrollView style={styles.transcriptScroll}>
                            {meeting.segments.map((seg, i) => {
                              const active = seg.start != null && currentTime >= seg.start && currentTime < seg.end;
                              return (
                                <Pressable
                                  key={i}
                                  style={[styles.segmentRow, active && styles.segmentRowActive]}
                                  onPress={() => seekTo(seg.start)}
                                >
                                  <View style={styles.segmentHeader}>
                                    {seg.start != null && <Text style={styles.segmentTime}>{formatElapsed(Math.floor(seg.start))}</Text>}
                                    <SpeakerBadge speaker={seg.speaker} />
                                  </View>
                                  <Text style={styles.segmentText}>{seg.text}</Text>
                                </Pressable>
                              );
                            })}
                          </ScrollView>
                        ) : meeting.fixed_transcript || meeting.transcript ? (
                          <ScrollView style={styles.transcriptScroll}>
                            {/* fixed_transcript is the LLM-corrected version — prefer it,
                                falling back to the raw transcript only if that step failed. */}
                            <Text style={styles.plainTranscript}>{meeting.fixed_transcript || meeting.transcript}</Text>
                          </ScrollView>
                        ) : (
                          <Text style={styles.errorText}>Transkrip gagal: {meeting.transcript_error || "tidak diketahui"}.</Text>
                        )}
                      </View>
                    </View>
                    {!meeting.segments && meeting.transcript && (
                      <Text style={styles.syncNote}>
                        Rapat ini direkam sebelum fitur sinkronisasi waktu ada, jadi transkrip tampil apa adanya tanpa
                        highlight per baris.
                      </Text>
                    )}
                  </View>
                )}

                {activeTab === "edit" && (
                  <View style={styles.section}>
                    <View style={styles.editorGrid}>
                      <View style={styles.editorCol}>
                        <Text style={styles.editorColTitle}>Transkrip Mentah</Text>
                        {meeting.transcript && (
                          <View style={styles.namesPanel}>
                            <View style={styles.namesHeader}>
                              <Feather name="users" size={14} color={colors.goldDeep} />
                              <Text style={styles.namesTitle}>Nama Pembicara</Text>
                            </View>
                            <Text style={styles.namesHint}>
                              Isi nama asli agar tampil di semua baris dan ringkasan setelah disimpan.
                            </Text>
                            <View style={styles.namesGrid}>
                              {[...new Set(editedLines.map((l) => l.speaker).filter(Boolean))].map((raw) => (
                                <SpeakerNameRow
                                  key={raw}
                                  raw={raw}
                                  name={speakerNames[raw] || ""}
                                  onCommit={(name) => {
                                    if (name !== (speakerNames[raw] || "")) setDirty(true);
                                    setSpeakerNames((m) => {
                                      const next = { ...m };
                                      if (name) next[raw] = name;
                                      else delete next[raw];
                                      return next;
                                    });
                                  }}
                                />
                              ))}
                            </View>
                          </View>
                        )}
                        {meeting.transcript ? (
                          <ScrollView ref={editorScrollRef} style={styles.editorLinesBox}>
                            {(() => {
                              const lineSpeakers = resolveLineSpeakers(editedLines, speakerNames, lineOverrides);
                              const rawLabels = [...new Set(editedLines.map((l) => l.speaker).filter(Boolean))];
                              const nameOf = (raw) => speakerNames[raw] || raw;
                              const pickOptions = [...new Set(rawLabels.map(nameOf))];
                              return editedLines.map((line, i) => (
                                <View
                                  key={i}
                                  style={[
                                    styles.editorLineRow,
                                    i === activeLine && styles.editorLineRowActive,
                                    mergeOpenIndex === i && styles.editorLineRowElevated,
                                  ]}
                                  ref={(el) => {
                                    lineEls.current[i] = el;
                                  }}
                                >
                                  {line.speaker && (
                                    <View style={styles.editorLineHeader}>
                                      {meeting.segments?.length === editedLines.length && meeting.segments[i].start != null && (
                                        <Pressable onPress={() => seekTo(meeting.segments[i].start)} hitSlop={6}>
                                          <Text style={styles.segmentTime}>{formatElapsed(Math.floor(meeting.segments[i].start))}</Text>
                                        </Pressable>
                                      )}
                                      <LineSpeakerBadge
                                        raw={line.speaker}
                                        value={lineSpeakers[i]}
                                        overridden={!!lineOverrides[i]}
                                        options={pickOptions.filter((l) => l !== lineSpeakers[i])}
                                        open={mergeOpenIndex === i}
                                        onToggle={() => setMergeOpenIndex((cur) => (cur === i ? null : i))}
                                        onPick={(name) => {
                                          setDirty(true);
                                          setLineOverrides((m) => {
                                            const next = { ...m };
                                            if (name === nameOf(line.speaker)) delete next[i];
                                            else next[i] = name;
                                            return next;
                                          });
                                          setMergeOpenIndex(null);
                                        }}
                                        onReset={() => {
                                          setDirty(true);
                                          setLineOverrides((m) => {
                                            const next = { ...m };
                                            delete next[i];
                                            return next;
                                          });
                                          setMergeOpenIndex(null);
                                        }}
                                      />
                                    </View>
                                  )}
                                  <LineTextarea
                                    value={line.text}
                                    onFocus={() => setFocusedLineIndex(i)}
                                    onChange={(text) => {
                                      setDirty(true);
                                      setEditedLines((lines) => lines.map((l, j) => (j === i ? { ...l, text } : l)));
                                    }}
                                  />
                                </View>
                              ));
                            })()}
                          </ScrollView>
                        ) : (
                          <View style={styles.editorRawBox}>
                            <Text style={styles.errorText}>
                              Transkrip gagal: {meeting.transcript_error || "tidak diketahui"}.
                            </Text>
                          </View>
                        )}
                      </View>

                      <View style={styles.editorCol}>
                        {meeting.recording && (
                          <video
                            ref={videoRef}
                            controls
                            style={{ width: "100%", borderRadius: radius.md, backgroundColor: "#000", maxHeight: 230, objectFit: "contain", display: "block" }}
                            src={getRecordingUrl(meeting.id)}
                            onTimeUpdate={(e) => setCurrentTime(e.target.currentTime)}
                            onPlay={() => setPlaying(true)}
                            onPause={() => setPlaying(false)}
                          />
                        )}
                        <View style={styles.editorColHeader}>
                          <Feather name="zap" size={13} color={colors.goldDeep} />
                          <Text style={styles.editorColTitle}>Saran Perbaikan AI</Text>
                        </View>
                        {(() => {
                          if (!meeting.fixed_transcript) {
                            return (
                              <View style={styles.suggestLinesBox}>
                                <Text style={styles.plainTranscript}>Belum ada saran perbaikan.</Text>
                              </View>
                            );
                          }
                          if (focusedLineIndex == null) {
                            return (
                              <View style={styles.suggestLinesBox}>
                                <Text style={styles.plainTranscript}>
                                  Klik salah satu baris di Transkrip Mentah untuk melihat saran perbaikan AI-nya di sini.
                                </Text>
                              </View>
                            );
                          }
                          // Assumes fixed_transcript kept the same line order/count as the
                          // raw transcript (fix_transcript() corrects wording, it doesn't
                          // restructure lines) — same assumption the segments sync already
                          // relies on (see updateTranscript's line_texts/line_speakers).
                          const suggestedLine = parseTranscriptLines(meeting.fixed_transcript)[focusedLineIndex];
                          if (!suggestedLine) {
                            return (
                              <View style={styles.suggestLinesBox}>
                                <Text style={styles.plainTranscript}>Tidak ada saran untuk baris ini.</Text>
                              </View>
                            );
                          }
                          return (
                            <View style={styles.suggestLinesBox}>
                              <View style={styles.suggestLineRow}>
                                {suggestedLine.speaker && <SpeakerBadge speaker={suggestedLine.speaker} />}
                                <Text style={styles.suggestLineText}>{suggestedLine.text}</Text>
                              </View>
                            </View>
                          );
                        })()}
                        <View style={styles.editorActions}>
                          {dirty && !savingTranscript && (
                            <Text style={styles.dirtyNoticeText}>
                              Ada perubahan yang belum disimpan. Ringkasan baru ikut berubah setelah kamu klik tombol di bawah.
                            </Text>
                          )}
                          {savedNotice && !dirty && (
                            <Text style={styles.savedNoticeText}>Tersimpan, ringkasan diperbarui.</Text>
                          )}
                          {!!saveError && <Text style={styles.errorText}>{saveError}</Text>}
                          <Pressable
                            style={[styles.saveButton, savingTranscript && styles.saveButtonDisabled]}
                            disabled={savingTranscript || editedLines.every((l) => !l.text.trim())}
                            onPress={handleSaveTranscript}
                          >
                            {savingTranscript ? (
                              <ActivityIndicator color={colors.ink} size="small" />
                            ) : (
                              <Feather name="check" size={13} color={colors.ink} />
                            )}
                            <Text style={styles.saveButtonLabel}>Simpan & Buat Ulang Ringkasan</Text>
                          </Pressable>
                        </View>
                      </View>
                    </View>
                  </View>
                )}
              </>
            )}
          </>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { alignItems: "center", padding: spacing.lg },
  content: { gap: spacing.md, maxWidth: 1200, width: "100%" },

  backLink: { ...type.small, color: colors.inkSoft },

  stateBox: { alignItems: "center", gap: spacing.sm, paddingVertical: spacing.xxl },
  stateText: { ...type.body, color: colors.inkSoft, textAlign: "center" },
  errorText: { ...type.body, color: colors.danger },

  headerCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  badgeRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  platformBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    backgroundColor: colors.surfaceSunken,
    borderRadius: radius.pill,
    paddingVertical: 5,
    paddingHorizontal: 10,
  },
  platformBadgeLabel: { ...type.small, color: colors.inkSoft },
  title: { ...type.h1, fontSize: 24, color: colors.ink },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 5 },
  metaText: { ...type.body, color: colors.inkSoft },
  metaIconGap: { marginLeft: spacing.md },

  // Live view
  liveCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
    alignItems: "center",
    gap: spacing.xl,
  },
  stepper: { flexDirection: "row", alignItems: "flex-start", alignSelf: "stretch", justifyContent: "center" },
  stepItemWrap: { flexDirection: "row", alignItems: "center" },
  stepItem: { alignItems: "center", gap: 6, width: 92 },
  stepDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.border },
  stepDotActive: { backgroundColor: colors.gold },
  stepLabel: { ...type.small, color: colors.inkFaint },
  stepLabelActive: { color: colors.ink, fontWeight: "600" },
  stepLine: { height: 2, width: 40, backgroundColor: colors.border, marginBottom: 16 },
  stepLineActive: { backgroundColor: colors.gold },

  liveCenter: { alignItems: "center", gap: spacing.sm },
  liveStatusRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  pulseDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.danger },
  liveStatusText: { ...type.bodyMedium, color: colors.ink },
  liveTimer: { fontSize: 48, fontWeight: "700", color: colors.ink, fontVariant: ["tabular-nums"], letterSpacing: -1 },

  stopButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: colors.danger,
    borderRadius: radius.sm,
    paddingVertical: 12,
    paddingHorizontal: spacing.xl,
  },
  stopButtonLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.white },

  liveInfoBox: {
    flexDirection: "row",
    gap: 8,
    backgroundColor: colors.goldSoft,
    borderRadius: radius.sm,
    padding: spacing.md,
    alignSelf: "stretch",
  },
  liveInfoText: { ...type.small, color: colors.goldDeep, flex: 1, lineHeight: 17, textAlign: "left" },

  liveFailedRow: { flexDirection: "row", alignItems: "center", gap: 10 },

  // Tab bar
  tabBar: {
    flexDirection: "row",
    backgroundColor: colors.surfaceSunken,
    borderRadius: radius.pill,
    padding: 4,
    gap: 4,
  },
  tabButton: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingVertical: 10,
    borderRadius: radius.pill,
  },
  tabButtonActive: { backgroundColor: colors.gold },
  tabLabel: { ...type.small, fontWeight: "600", color: colors.inkFaint },
  tabLabelActive: { color: colors.ink },

  section: { gap: spacing.md },

  summaryCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
  },
  summaryCardHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm },
  iconWrap: {
    width: 30,
    height: 30,
    borderRadius: radius.sm,
    backgroundColor: colors.goldSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  summaryCardLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },
  kbButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
  },
  kbButtonOn: { backgroundColor: colors.goldSoft, borderColor: colors.gold },
  kbButtonLabel: { ...type.small, fontWeight: "600", color: colors.ink },
  summaryText: { ...type.body, color: colors.inkSoft, lineHeight: 21 },

  twoCol: { flexDirection: "row", gap: spacing.lg },
  colCard: {
    flex: 1,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  colTitle: { ...type.h2, color: colors.ink, marginBottom: 2 },
  decisionRow: { flexDirection: "row", alignItems: "flex-start", gap: 8 },
  decisionText: { ...type.body, color: colors.inkSoft, flex: 1, lineHeight: 20 },
  topicRow: { flexDirection: "row", alignItems: "flex-start", gap: 10 },
  topicIndex: {
    ...type.small,
    fontWeight: "700",
    color: colors.goldDeep,
    backgroundColor: colors.goldSoft,
    width: 20,
    height: 20,
    borderRadius: 10,
    textAlign: "center",
    lineHeight: 20,
  },
  topicText: { ...type.body, color: colors.inkSoft, flex: 1, lineHeight: 20 },

  actionItemsCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  actionItemsHeader: { flexDirection: "row", alignItems: "center" },
  itemForm: {
    gap: spacing.sm,
    padding: spacing.sm,
    borderWidth: 1,
    borderColor: colors.gold,
    borderRadius: radius.sm,
    backgroundColor: colors.bg,
  },
  itemInput: {
    ...type.small,
    color: colors.ink,
    paddingVertical: 6,
    paddingHorizontal: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    outlineStyle: "none",
  },
  smallButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingVertical: 5,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  smallButtonPrimary: { backgroundColor: colors.gold, borderColor: colors.gold },
  smallButtonDanger: { backgroundColor: colors.danger, borderColor: colors.danger },
  smallButtonLabel: { ...type.small, fontWeight: "600", color: colors.ink },
  actionItemRow: { flexDirection: "row", alignItems: "flex-start", gap: 10 },
  actionItemTask: { ...type.body, color: colors.ink, lineHeight: 20 },
  actionItemTaskDone: { color: colors.inkFaint, textDecorationLine: "line-through" },
  actionItemMeta: { ...type.small, color: colors.inkFaint, marginTop: 2 },

  mediaGrid: { flexDirection: "row", gap: spacing.lg, alignItems: "flex-start" },
  videoCol: { flex: 1.1, gap: spacing.sm },
  fileInfoRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  fileInfoText: { ...type.small, color: colors.inkFaint },
  downloadBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: 7,
    paddingHorizontal: 12,
  },
  downloadLabel: { ...type.small, fontWeight: "600", color: colors.ink },

  transcriptCol: {
    flex: 1,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    overflow: "hidden",
  },
  transcriptScroll: { maxHeight: 420, padding: spacing.md },
  segmentRow: {
    gap: 4,
    padding: spacing.sm,
    borderRadius: radius.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  segmentRowActive: { backgroundColor: colors.goldSoft, borderBottomColor: "transparent" },
  segmentHeader: { flexDirection: "row", alignItems: "center", gap: 8 },
  segmentTime: { ...type.small, color: colors.inkFaint, fontVariant: ["tabular-nums"] },
  segmentText: { ...type.body, color: colors.ink, lineHeight: 20 },
  speakerBadgeWrap: { position: "relative", alignSelf: "flex-start" },
  speakerBadge: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    borderRadius: radius.pill,
    paddingVertical: 2,
    paddingHorizontal: 8,
  },
  speakerBadgeLabel: { ...type.small, fontWeight: "700" },
  speakerScopeToggle: { paddingVertical: 1 },
  namesPanel: {
    gap: 4,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    ...shadow.card,
  },
  namesHeader: { flexDirection: "row", alignItems: "center", gap: 6 },
  namesTitle: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },
  namesHint: { ...type.small, color: colors.inkFaint },
  namesGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs },
  nameCell: { flexGrow: 1, flexBasis: 100, minWidth: 100, gap: 4 },
  nameCellLabel: { flexDirection: "row", alignItems: "center", gap: 6 },
  nameCellRaw: { ...type.small, fontWeight: "700", letterSpacing: 0.3 },
  nameInput: {
    ...type.body,
    color: colors.ink,
    paddingVertical: 7,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.bg,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    outlineStyle: "none",
  },
  nameInputFilled: { backgroundColor: colors.goldSoft, borderColor: colors.gold, fontWeight: "600" },
  speakerBadgeInput: { ...type.small, fontWeight: "700", padding: 0, minWidth: 60, outlineStyle: "none" },
  mergeMenu: {
    position: "absolute",
    top: "100%",
    left: 0,
    marginTop: 4,
    zIndex: 10,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    padding: spacing.xs,
    minWidth: 140,
    ...shadow.card,
  },
  mergeMenuLabel: { ...type.small, color: colors.inkFaint, paddingHorizontal: spacing.xs, paddingBottom: 2 },
  mergeMenuItem: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 5, paddingHorizontal: spacing.xs, borderRadius: radius.sm },
  mergeMenuDot: { width: 8, height: 8, borderRadius: 4 },
  mergeMenuItemLabel: { ...type.small, fontWeight: "600", color: colors.ink },
  syncNote: { ...type.small, color: colors.inkFaint, fontStyle: "italic" },

  // Transcript editor (Transkrip tab)
  editorGrid: { flexDirection: "row", gap: spacing.xl, alignItems: "flex-start" },
  editorCol: { flex: 1, gap: spacing.md },
  editorColHeader: { flexDirection: "row", alignItems: "center", gap: 6 },
  editorColTitle: { ...type.h2, color: colors.ink },
  editorRawBox: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    minHeight: 360,
  },
  editorScroll: { maxHeight: 420 },
  plainTranscript: { ...type.small, color: colors.inkSoft, lineHeight: 19 },
  editorLinesBox: {
    maxHeight: 460,
    minHeight: 320,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.gold,
    borderRadius: radius.md,
    padding: spacing.sm,
  },
  editorLineRow: {
    gap: 4,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  // z-index only wins against siblings within the same stacking context —
  // without this, the "gabung ke" dropdown (position: absolute, zIndex: 10
  // inside speakerBadgeWrap) still rendered underneath the next row, since
  // that row is a separate, later-painted sibling with no z-index of its
  // own. Lifting the whole open row above its siblings fixes it.
  editorLineRowElevated: { position: "relative", zIndex: 20 },
  editorLineHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  editorLineRowActive: { backgroundColor: colors.goldSoft, borderLeftWidth: 3, borderLeftColor: colors.gold },
  // Right column's read-only counterpart to editorLinesBox/editorLineRow —
  // same per-speaker-line layout so the two columns read as one continuous
  // idea, but deliberately undecorated (muted bg instead of the left's gold
  // "this is editable" border, no per-line divider, no input/merge affordances)
  // so it doesn't look like a second editable form.
  suggestLinesBox: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  suggestLineRow: { gap: spacing.sm },
  suggestLineText: { ...type.body, fontSize: 14, color: colors.ink, lineHeight: 20 },
  editorLineInput: {
    ...type.body,
    color: colors.ink,
    lineHeight: 20,
    padding: 0,
    textAlignVertical: "top",
    outlineStyle: "none",
  },
  editorActions: { gap: spacing.sm, alignItems: "stretch" },
  savedNoticeText: { ...type.small, color: colors.success },
  dirtyNoticeText: { ...type.small, color: colors.goldDeep, fontWeight: "600" },
  saveButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    backgroundColor: colors.gold,
    borderRadius: radius.sm,
    paddingVertical: 8,
    paddingHorizontal: spacing.md,
  },
  saveButtonDisabled: { opacity: 0.6 },
  saveButtonLabel: { ...type.small, fontWeight: "700", color: colors.ink },
});
