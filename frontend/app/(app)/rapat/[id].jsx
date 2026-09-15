import { Feather } from "@expo/vector-icons";
import { Link, useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState } from "react";
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
import { getJobStatus, getMeeting, getRecordingUrl, stopJob, toggleActionItem, updateTranscript } from "@/lib/api";
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

function SpeakerBadge({ speaker }) {
  const color = speakerColor(speaker);
  return (
    <View style={[styles.speakerBadge, { backgroundColor: `${color}22` }]}>
      <Text style={[styles.speakerBadgeLabel, { color }]}>{speaker}</Text>
    </View>
  );
}

// Editable variant used only in the transcript editor — color keys off the
// currently-displayed value (not the raw speaker id), so two speakers
// merged into the same name immediately show the same color instead of
// only matching after a save+reload. The users/user icon toggles whether
// typing here renames this speaker id everywhere (isGlobal) or just this
// one line (diarization sometimes mis-attributes a single line to the
// wrong speaker cluster). The merge icon opens a pick-list of the other
// speaker names already used in this transcript, so merging two
// over-segmented clusters doesn't require retyping the name identically.
function EditableSpeakerBadge({ speaker, value, isGlobal, onToggleGlobal, onChangeText, otherLabels, mergeOpen, onToggleMerge, onMerge }) {
  const color = speakerColor(value);
  return (
    <View style={styles.speakerBadgeWrap}>
      <View style={[styles.speakerBadge, { backgroundColor: `${color}22` }]}>
        <Pressable onPress={onToggleGlobal} style={styles.speakerScopeToggle} hitSlop={6}>
          <Feather name={isGlobal ? "users" : "user"} size={11} color={color} />
        </Pressable>
        <TextInput style={[styles.speakerBadgeInput, { color }]} value={value} onChangeText={onChangeText} />
        {otherLabels.length > 0 && (
          <Pressable onPress={onToggleMerge} style={styles.speakerScopeToggle} hitSlop={6}>
            <Feather name="git-merge" size={11} color={color} />
          </Pressable>
        )}
      </View>
      {mergeOpen && (
        <View style={styles.mergeMenu}>
          <Text style={styles.mergeMenuLabel}>Gabung ke:</Text>
          {otherLabels.map((label) => (
            <Pressable key={label} style={styles.mergeMenuItem} onPress={() => onMerge(label)}>
              <View style={[styles.mergeMenuDot, { backgroundColor: speakerColor(label) }]} />
              <Text style={styles.mergeMenuItemLabel}>{label}</Text>
            </Pressable>
          ))}
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
  // { <line index>: boolean } — whether that line's badge, when edited,
  // renames the speaker id everywhere (true, default) or just that line
  // (false). Per-line so different lines of the same speaker can be in
  // different modes at once.
  const [lineIsGlobal, setLineIsGlobal] = useState({});
  // Which line's "gabung ke speaker lain" pick-list is open — only one at
  // a time, since it's rendered inline right under that line's badge.
  const [mergeOpenIndex, setMergeOpenIndex] = useState(null);
  const [savingTranscript, setSavingTranscript] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [savedNotice, setSavedNotice] = useState(false);

  useEffect(() => () => clearTimeout(pollTimer.current), []);

  useEffect(() => {
    getMeeting(id)
      .then((data) => {
        setMeeting(data);
        setEditedLines(parseTranscriptLines(data.transcript));
        setSpeakerNames({});
        setLineOverrides({});
        setLineIsGlobal({});
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

  function poll(jobId) {
    getJobStatus(jobId)
      .then((data) => {
        setLiveStatus(data.status);
        if (data.elapsed_seconds != null) setElapsed(data.elapsed_seconds);
        if (data.status === "done") {
          // Re-fetch the canonical, now-finished record instead of trying to
          // reconstruct it from the job response — same data a page reload
          // would show, and picks up segments/file info the job response
          // never carried.
          getMeeting(id).then((fresh) => {
            setMeeting(fresh);
            setEditedLines(parseTranscriptLines(fresh.transcript));
            setSpeakerNames({});
            setLineOverrides({});
            setLineIsGlobal({});
            setLiveStatus(null);
          });
        } else if (data.status === "failed") {
          setLiveError(data.error || "Terjadi kesalahan");
        } else {
          pollTimer.current = setTimeout(() => poll(jobId), 1000);
        }
      })
      .catch((e) => {
        setLiveError(e.message || "Gagal memuat status rekaman");
        setLiveStatus("failed");
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
    } catch (e) {
      setSaveError(e.message || "Gagal menyimpan transkrip");
    } finally {
      setSavingTranscript(false);
    }
  }

  function handleToggleActionItem(index) {
    // Optimistic — flip it locally right away, reconcile with whatever the
    // server actually persisted once the request comes back (same file on
    // disk, so this should always agree, but never trust just the optimism).
    setMeeting((m) => ({
      ...m,
      summary: {
        ...m.summary,
        action_items: m.summary.action_items.map((item, i) =>
          i === index ? { ...item, done: !item.done } : item
        ),
      },
    }));
    toggleActionItem(id, index)
      .then((summary) => setMeeting((m) => ({ ...m, summary })))
      .catch(() => {
        // Revert on failure — flip it back rather than leaving the UI
        // showing a state the server never actually saved.
        setMeeting((m) => ({
          ...m,
          summary: {
            ...m.summary,
            action_items: m.summary.action_items.map((item, i) =>
              i === index ? { ...item, done: !item.done } : item
            ),
          },
        }));
      });
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
                          <Text style={styles.summaryCardLabel}>Executive Summary</Text>
                        </View>
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

                      {meeting.summary.action_items?.length > 0 && (
                        <View style={styles.actionItemsCard}>
                          <Text style={styles.colTitle}>Action Items</Text>
                          {meeting.summary.action_items.map((item, i) => (
                            <Pressable
                              key={i}
                              style={styles.actionItemRow}
                              onPress={() => handleToggleActionItem(i)}
                            >
                              <Feather
                                name={item.done ? "check-square" : "square"}
                                size={15}
                                color={item.done ? colors.success : colors.inkFaint}
                                style={{ marginTop: 2 }}
                              />
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
                            </Pressable>
                          ))}
                        </View>
                      )}
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
                        {meeting.transcript ? (
                          <ScrollView style={styles.editorLinesBox}>
                            {(() => {
                              const lineSpeakers = resolveLineSpeakers(editedLines, speakerNames, lineOverrides);
                              const applyName = (i, name) => {
                                if (lineIsGlobal[i] ?? true) {
                                  setSpeakerNames((m) => ({ ...m, [editedLines[i].speaker]: name }));
                                } else {
                                  setLineOverrides((m) => ({ ...m, [i]: name }));
                                }
                              };
                              return editedLines.map((line, i) => (
                                <View
                                  key={i}
                                  style={[styles.editorLineRow, mergeOpenIndex === i && styles.editorLineRowElevated]}
                                >
                                  {line.speaker && (
                                    <View style={styles.editorLineHeader}>
                                      <EditableSpeakerBadge
                                        speaker={line.speaker}
                                        value={lineSpeakers[i]}
                                        isGlobal={lineIsGlobal[i] ?? true}
                                        onToggleGlobal={() =>
                                          setLineIsGlobal((m) => ({ ...m, [i]: !(m[i] ?? true) }))
                                        }
                                        onChangeText={(name) => applyName(i, name)}
                                        otherLabels={[...new Set(lineSpeakers.filter((l, j) => l && j !== i && l !== lineSpeakers[i]))]}
                                        mergeOpen={mergeOpenIndex === i}
                                        onToggleMerge={() => setMergeOpenIndex((cur) => (cur === i ? null : i))}
                                        onMerge={(name) => {
                                          applyName(i, name);
                                          setMergeOpenIndex(null);
                                        }}
                                      />
                                    </View>
                                  )}
                                  <TextInput
                                    style={styles.editorLineInput}
                                    multiline
                                    value={line.text}
                                    onChangeText={(text) =>
                                      setEditedLines((lines) => lines.map((l, j) => (j === i ? { ...l, text } : l)))
                                    }
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
                        <View style={styles.editorColHeader}>
                          <Feather name="zap" size={13} color={colors.goldDeep} />
                          <Text style={styles.editorColTitle}>Saran Perbaikan AI</Text>
                        </View>
                        <View style={styles.editorRawBox}>
                          <ScrollView style={styles.editorScroll}>
                            <Text style={styles.plainTranscript}>
                              {meeting.fixed_transcript || "Belum ada saran perbaikan."}
                            </Text>
                          </ScrollView>
                        </View>
                        <View style={styles.editorActions}>
                          {savedNotice && <Text style={styles.savedNoticeText}>Tersimpan, ringkasan diperbarui.</Text>}
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
  scrollContent: { alignItems: "center", padding: spacing.xxl },
  content: { gap: spacing.xl, maxWidth: 1100, width: "100%" },

  backLink: { ...type.small, color: colors.inkSoft },

  stateBox: { alignItems: "center", gap: spacing.sm, paddingVertical: spacing.xxl },
  stateText: { ...type.body, color: colors.inkSoft, textAlign: "center" },
  errorText: { ...type.body, color: colors.danger },

  headerCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.xl,
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
  title: { ...type.display, color: colors.ink },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 5 },
  metaText: { ...type.body, color: colors.inkSoft },
  metaIconGap: { marginLeft: spacing.md },

  // Live view
  liveCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.xxl,
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
    padding: spacing.xl,
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
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    borderRadius: radius.pill,
    paddingVertical: 2,
    paddingHorizontal: 8,
  },
  speakerBadgeLabel: { ...type.small, fontWeight: "700" },
  speakerScopeToggle: { paddingVertical: 1 },
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
  editorGrid: { flexDirection: "row", gap: spacing.lg, alignItems: "stretch" },
  editorCol: { flex: 1, gap: spacing.sm },
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
    maxHeight: 420,
    minHeight: 360,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.gold,
    borderRadius: radius.md,
    padding: spacing.sm,
  },
  editorLineRow: {
    gap: 4,
    padding: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  // z-index only wins against siblings within the same stacking context —
  // without this, the "gabung ke" dropdown (position: absolute, zIndex: 10
  // inside speakerBadgeWrap) still rendered underneath the next row, since
  // that row is a separate, later-painted sibling with no z-index of its
  // own. Lifting the whole open row above its siblings fixes it.
  editorLineRowElevated: { position: "relative", zIndex: 20 },
  editorLineHeader: { flexDirection: "row" },
  editorLineInput: {
    ...type.body,
    color: colors.ink,
    lineHeight: 20,
    padding: 0,
    textAlignVertical: "top",
    outlineStyle: "none",
  },
  editorActions: { gap: spacing.sm, alignItems: "flex-end" },
  savedNoticeText: { ...type.small, color: colors.success },
  saveButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    backgroundColor: colors.gold,
    borderRadius: radius.sm,
    paddingVertical: 10,
    paddingHorizontal: spacing.lg,
  },
  saveButtonDisabled: { opacity: 0.6 },
  saveButtonLabel: { ...type.small, fontWeight: "700", color: colors.ink },
});
