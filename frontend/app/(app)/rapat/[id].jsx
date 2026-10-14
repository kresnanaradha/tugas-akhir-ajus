import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
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
import { deleteMeeting, generateShortSummary, getJobStatus, getMeeting, getRecordingUrl, processMeeting, replaceActionItems, setKnowledgeBase, shareMeetingWithTeam, stopJob, toggleActionItem, updateTranscript } from "@/lib/api";
import { formatMeetingDate, PLATFORM_LABEL } from "@/lib/format";
import { buildEditorState, formatBytes, formatElapsed, joinTranscriptLines, meetingStats, parseTranscriptLines, resolveLineSpeakers, speakerColor } from "@/lib/transcript";
import { BackLink } from "@/components/BackLink";
import { StatCard } from "@/components/StatCard";
import { StatusPill } from "@/components/StatusPill";
import { useAuth } from "@/lib/auth-context";

function SpeakerBadge({ speaker }) {
  const color = speakerColor(speaker);
  return (
    <View style={[styles.speakerBadge, { backgroundColor: `${color}22` }]}>
      <Text style={[styles.speakerBadgeLabel, { color }]}>{speaker}</Text>
    </View>
  );
}

// <textarea> mentah (hanya web) yang tumbuh sesuai teksnya: TextInput multiline RN selalu menyisakan dua baris, yang meninggalkan
// celah di bawah setiap baris satu garis
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

// satu baris panel nama pembicara: mengganti nama id pembicara di mana-mana. Menyimpan draf dan menyimpan saat blur atau enter, jadi
// baris tidak berubah saat mengetik. Kosong = kembali ke id mentah
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

// badge per baris: klik untuk memindahkan hanya baris ini ke pembicara lain. Mengganti nama satu pembicara penuh dilakukan di panel di atas
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

// polling menyerah setelah sekian permintaan gagal berturut-turut. Permintaan gagal tidak memberi tahu apa-apa soal job-nya (gangguan,
// Docker lambat), hanya respons 200 dengan status "failed" yang memberi tahu, jadi ia mencoba lagi daripada membekukan halaman
const MAX_CONSECUTIVE_POLL_FAILURES = 10;
const LIVE_STATUSES = ["joining", "recording", "stopping", "processing"];
const STEPS = [
  { key: "joining", label: "Bergabung" },
  { key: "recording", label: "Merekam" },
  { key: "processing", label: "Memproses" },
];
const STEP_INDEX = { joining: 0, recording: 1, stopping: 1, processing: 2 };

const TABS = [
  { key: "ringkasan", label: "Pokok Pembahasan Rapat", icon: "zap" },
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
  const { user } = useAuth();
  const [sharingTeam, setSharingTeam] = useState(false);
  const [screenStatus, setScreenStatus] = useState("loading"); // loading | error | done
  const [meeting, setMeeting] = useState(null);
  const [error, setError] = useState("");
  const [currentTime, setCurrentTime] = useState(0);
  const videoRef = useRef(null);
  const [activeTab, setActiveTab] = useState("ringkasan");

  // State job langsung (hanya relevan saat meeting.status salah satu dari LIVE_STATUSES)
  const [liveStatus, setLiveStatus] = useState(null); // null kalau sudah selesai/tidak live
  const [elapsed, setElapsed] = useState(0);
  const [liveError, setLiveError] = useState("");
  const pollTimer = useRef(null);
  const pollFailures = useRef(0);

  // Tab Edit Transkrip: transkrip mentah sebagai baris yang bisa diedit (kiri) dengan versi perbaikan AI sebagai acuan (kanan)
  const [editedLines, setEditedLines] = useState([]);
  // { SPEAKER_00: "Kresna" }: mengganti nama pembicara di mana-mana, berkunci id aslinya supaya warna badge tetap
  const [speakerNames, setSpeakerNames] = useState({});
  // { <indeks baris>: "Diva" }: memindahkan satu baris ke pembicara lain, saat diarization salah hanya di baris itu
  const [lineOverrides, setLineOverrides] = useState({});
  // baris yang daftar "pindahkan ke pembicara"-nya terbuka (satu pada satu waktu)
  const [mergeOpenIndex, setMergeOpenIndex] = useState(null);
  // baris yang sedang diedit: "Saran Perbaikan AI" hanya menampilkan versi AI untuk satu baris itu
  const [focusedLineIndex, setFocusedLineIndex] = useState(null);
  const [savingTranscript, setSavingTranscript] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [kbSaving, setKbSaving] = useState(false);
  const [kbError, setKbError] = useState("");
  const [processBusy, setProcessBusy] = useState(false);
  const [processError, setProcessError] = useState("");
  const [shortBusy, setShortBusy] = useState(false);
  const [shortError, setShortError] = useState("");
  const [savedNotice, setSavedNotice] = useState(false);
  // Edit (nama, baris dipindah, teks) yang belum disimpan: ringkasan hanya berubah saat disimpan.
  const [dirty, setDirty] = useState(false);
  const router = useRouter();
  // Editor action item: item mana yang sedang diedit (indeks, "new", atau null) + drafnya.
  const [editingItem, setEditingItem] = useState(null);
  const [itemDraft, setItemDraft] = useState({ task: "", assignee: "", due: "" });
  const [itemSaving, setItemSaving] = useState(false);
  const [itemError, setItemError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  // baris tempat video berada (baris dipetakan ke segmen lewat indeks, jadi hanya kalau jumlahnya sama)
  const [playing, setPlaying] = useState(false);
  const editorScrollRef = useRef(null);
  const lineEls = useRef({});
  const activeLine =
    meeting?.segments && meeting.segments.length === editedLines.length
      ? meeting.segments.findIndex((seg) => seg.start != null && currentTime >= seg.start && currentTime < seg.end)
      : -1;
  // Ikuti video hanya saat diputar, supaya tidak pernah berebut dengan user yang mengetik.
  useEffect(() => {
    // Aplikasi web saja: ukur node DOM baris terhadap kotak scroll langsung.
    const box = editorScrollRef.current?.getScrollableNode?.();
    const row = lineEls.current[activeLine];
    if (playing && box && row) {
      const top = row.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop - 40;
      box.scrollTop = Math.max(0, top);
    }
  }, [activeLine, playing]);

  useEffect(() => () => clearTimeout(pollTimer.current), []);

  // meeting yang dimuat juga mengembalikan editor ke yang tersimpan
  function showMeeting(data) {
    setMeeting(data);
    const editor = buildEditorState(data);
    setEditedLines(editor.lines);
    setSpeakerNames(editor.names);
    setLineOverrides(editor.overrides);
  }

  useEffect(() => {
    getMeeting(id)
      .then((data) => {
        showMeeting(data);
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

  // GET /jobs/<id> hanya tahu job di memori proses server itu, jadi 404 bukan berarti gagal (restart, worker
  // lain). Baris rapat punya status yang sebenarnya: pantau itu sampai tidak live lagi.
  function pollMeeting() {
    getMeeting(id)
      .then((fresh) => {
        if (LIVE_STATUSES.includes(fresh.status)) {
          setLiveStatus(fresh.status);
          pollTimer.current = setTimeout(pollMeeting, 3000);
          return;
        }
        showMeeting(fresh);
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
        if (data.status === "failed") {
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
    // kirim dan lupakan, polling berikutnya menunjukkan status sebenarnya. Perlu .catch: stop yang tiba setelah job selesai
    // mendapat 404 dan akan menjatuhkan halaman saat dev
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
      // ringkasan dibuat ulang dari transkrip yang baru dikoreksi user
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
    // optimistis, dan state lokal menang: permintaan membawa nilai yang diinginkan dan responsnya diabaikan (bisa lebih lama
    // dari klik berikutnya), jadi centang cepat berturut-turut tidak saling membatalkan. Hanya item ini yang dikembalikan kalau gagal
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

  async function handleShortSummary() {
    setShortBusy(true);
    setShortError("");
    try {
      const summary = await generateShortSummary(id);
      setMeeting((m) => ({ ...m, summary }));
    } catch (e) {
      setShortError(e.message || "Gagal membuat ringkasan");
    } finally {
      setShortBusy(false);
    }
  }

  // Rekaman yang disimpan tanpa AI (Free, melewati menit minggu ini): serahkan ke transkriber.
  async function handleProcessNow() {
    setProcessBusy(true);
    setProcessError("");
    try {
      await processMeeting(id);
      setMeeting((m) => ({ ...m, status: "processing" }));
      setLiveStatus("processing");
      pollMeeting();
    } catch (e) {
      setProcessError(e.message || "Gagal memulai pemrosesan");
    } finally {
      setProcessBusy(false);
    }
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

  function handleToggleShareTeam() {
    const enabled = !meeting.shared_with_team;
    setSharingTeam(true);
    shareMeetingWithTeam(id, enabled)
      .then(() => setMeeting((m) => ({ ...m, shared_with_team: enabled })))
      .catch(() => {})
      .finally(() => setSharingTeam(false));
  }

  const stats = meetingStats(meeting || {});
  const isLive = liveStatus && liveStatus !== "failed";
  const isLiveFailed = liveStatus === "failed";
  const stepIndex = STEP_INDEX[liveStatus] ?? 0;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <BackLink label="Kembali ke Daftar Rapat" />

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
                {!isLive && !confirmDelete && user?.team_id && meeting.user_id === user.id && (
                  <Pressable
                    style={[styles.smallButton, meeting.shared_with_team && styles.kbButtonOn, { marginLeft: "auto" }]}
                    onPress={handleToggleShareTeam}
                    disabled={sharingTeam}
                  >
                    <Feather name={meeting.shared_with_team ? "check" : "users"} size={12} color={colors.ink} />
                    <Text style={styles.smallButtonLabel}>
                      {meeting.shared_with_team ? "Dibagikan ke Team" : "Bagikan ke Team"}
                    </Text>
                  </Pressable>
                )}
                {!isLive && !confirmDelete && (
                  <Pressable
                    style={[styles.smallButton, !(user?.team_id && meeting.user_id === user?.id) && { marginLeft: "auto" }]}
                    onPress={() => setConfirmDelete(true)}
                  >
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

            {/* Tampilan live - bot masih bergabung/merekam/memproses */}
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

            {/* Job live gagal sebelum menghasilkan apa pun */}
            {isLiveFailed && (
              <View style={styles.liveCard}>
                <View style={styles.liveFailedRow}>
                  <Feather name="alert-circle" size={20} color={colors.danger} />
                  <Text style={styles.errorText}>{liveError || "Bot gagal bergabung ke rapat."}</Text>
                </View>
              </View>
            )}

            {/* Direkam dan disimpan, tapi tidak diproses AI (Free, melewati menit minggu ini) */}
            {!isLive && !isLiveFailed && meeting.status === "limited" && (
              <View style={styles.liveCard}>
                <View style={styles.liveFailedRow}>
                  <Feather name="info" size={20} color={colors.goldDeep} />
                  <Text style={[styles.summaryText, { flex: 1 }]}>
                    Rekaman rapat ini ({meeting.duration_minutes} menit) tersimpan utuh dan bisa diputar, tetapi belum dibuatkan
                    transkrip dan ringkasan AI karena melewati sisa kuota Free minggu ini. Upgrade ke Pro lalu klik Proses
                    Sekarang, atau proses setelah kuota baru tersedia (Minggu pukul 08.00) bila cukup.
                  </Text>
                </View>
                <video
                  controls
                  style={{ width: "100%", borderRadius: radius.md, backgroundColor: "#000", aspectRatio: "16/9" }}
                  src={getRecordingUrl(meeting.id)}
                />
                {(meeting.user_id === user?.id || user?.role === "super_admin") && (
                  <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: spacing.sm }}>
                    <Pressable style={styles.kbButton} onPress={() => router.push("/billing")}>
                      <Feather name="zap" size={13} color={colors.ink} />
                      <Text style={styles.kbButtonLabel}>Upgrade ke Pro</Text>
                    </Pressable>
                    <Pressable style={styles.smallButton} onPress={handleProcessNow} disabled={processBusy}>
                      <Feather name="play" size={12} color={colors.ink} />
                      <Text style={styles.smallButtonLabel}>{processBusy ? "Memulai..." : "Proses Sekarang"}</Text>
                    </Pressable>
                    {!!processError && <Text style={styles.errorText}>{processError}</Text>}
                  </View>
                )}
              </View>
            )}

            {/* Selesai - tab Ringkasan AI / Transkrip / Rekaman */}
            {!isLive && !isLiveFailed && meeting.status !== "limited" && (
              <>
                <View style={styles.statRow}>
                  <StatCard value={meeting.duration_minutes != null ? `${meeting.duration_minutes} mnt` : "-"} label="Durasi rekaman" />
                  <StatCard value={String(stats.speakerCount)} label="Pembicara terdeteksi" />
                  <StatCard value={stats.words.toLocaleString("id-ID")} label="Kata ditranskripsi" />
                  <StatCard value={`${stats.actionDone}/${stats.actionTotal}`} label="Action item selesai" />
                  <StatCard value={String(stats.decisions)} label="Keputusan utama" />
                </View>

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
                      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "flex-end", gap: spacing.sm }}>
                        {!!kbError && <Text style={styles.errorText}>{kbError}</Text>}
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

                      <View style={styles.summaryCard}>
                        <View style={styles.summaryCardHeader}>
                          <View style={styles.iconWrap}>
                            <Feather name="file-text" size={16} color={colors.goldDeep} />
                          </View>
                          <Text style={[styles.summaryCardLabel, { flex: 1 }]}>Ringkasan</Text>
                        </View>
                        {meeting.summary.short_summary ? (
                          <Text style={styles.summaryText}>{meeting.summary.short_summary}</Text>
                        ) : (
                          <View style={{ gap: spacing.sm, alignItems: "flex-start" }}>
                            <Text style={styles.actionItemMeta}>Rapat ini diringkas sebelum ringkasan singkat ada.</Text>
                            <Pressable style={styles.smallButton} onPress={handleShortSummary} disabled={shortBusy}>
                              <Feather name="zap" size={12} color={colors.ink} />
                              <Text style={styles.smallButtonLabel}>{shortBusy ? "Membuat..." : "Buat ringkasan singkat"}</Text>
                            </Pressable>
                            {!!shortError && <Text style={styles.errorText}>{shortError}</Text>}
                          </View>
                        )}
                      </View>

                      <View style={styles.summaryCard}>
                        <View style={styles.summaryCardHeader}>
                          <View style={styles.iconWrap}>
                            <Feather name="zap" size={16} color={colors.goldDeep} />
                          </View>
                          <Text style={[styles.summaryCardLabel, { flex: 1 }]}>Pokok Pembahasan Rapat</Text>
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
                              {/* seluruh sisi kiri (kotak centang dan teks) bisa diketuk, ikon kecil saja mudah terlewat */}
                              <Pressable style={styles.actionItemMain} onPress={() => handleToggleActionItem(i)}>
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
                              <Pressable onPress={() => startEditItem(i)} hitSlop={10}>
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
                        {/* <video> mentah (aplikasi web saja): kontrol bawaan browser menangani putar, geser, dan durasi */}
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
                          {/* <a download> mentah: unduhan file biasa */}
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
                            {/* transkrip perbaikan AI kalau ada, kalau tidak yang mentah */}
                            <Text style={styles.plainTranscript}>{meeting.fixed_transcript || meeting.transcript}</Text>
                          </ScrollView>
                        ) : (
                          <Text style={styles.errorText}>{meeting.transcript_error ? `Transkrip gagal: ${meeting.transcript_error}.` : "Tidak ada percakapan yang terdeteksi dalam rekaman ini."}</Text>
                        )}
                      </View>
                    </View>
                    {!meeting.segments && !!meeting.transcript && (
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
                        {!!meeting.transcript && (
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
                              {meeting.transcript_error ? `Transkrip gagal: ${meeting.transcript_error}.` : "Tidak ada percakapan yang terdeteksi dalam rekaman ini."}
                            </Text>
                          </View>
                        )}
                      </View>

                      <View style={styles.editorCol}>
                        {!!meeting.recording && (
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
                          // fixed_transcript mempertahankan urutan dan jumlah baris transkrip mentah (perbaikan hanya mengubah kata)
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
  scrollContent: { alignItems: "center", paddingVertical: spacing.lg, paddingHorizontal: "5%" },
  content: { gap: spacing.md, width: "100%" },

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

  // Tampilan live
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

  // Bilah tab
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

  statRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  twoCol: { flexDirection: "row", flexWrap: "wrap", gap: spacing.lg },
  colCard: {
    flex: 1,
    minWidth: 260,
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
  actionItemMain: { flex: 1, flexDirection: "row", alignItems: "flex-start", gap: 10 },
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

  // Editor transkrip (tab Transkrip)
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
  // z-index hanya menang di dalam satu stacking context: mengangkat seluruh baris yang terbuka menjaga dropdown "pindahkan ke" di atas baris berikutnya
  editorLineRowElevated: { position: "relative", zIndex: 20 },
  editorLineHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  editorLineRowActive: { backgroundColor: colors.goldSoft, borderLeftWidth: 3, borderLeftColor: colors.gold },
  // pasangan read-only dari editorLinesBox/editorLineRow: tata letak sama, tapi diredupkan supaya tidak terlihat seperti form kedua
  suggestLinesBox: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  suggestLineRow: { gap: spacing.sm },
  suggestLineText: { ...type.body, fontSize: 14, color: colors.ink, lineHeight: 20 },
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
