import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";

import { colors, radius, spacing } from "@/constants/theme";
import { deleteMeeting, getJobStatus, getMeeting, getRecordingUrl, processMeeting, shareMeetingWithTeam, stopJob } from "@/lib/api";
import { formatMeetingDate, PLATFORM_LABEL } from "@/lib/format";
import { meetingStats } from "@/lib/transcript";
import { BackLink } from "@/components/BackLink";
import { StatCard } from "@/components/StatCard";
import { StatusPill } from "@/components/StatusPill";
import { ConfirmModal } from "@/components/ConfirmModal";
import { EditorTab } from "@/components/rapat/EditorTab";
import { LiveStatusCard } from "@/components/rapat/LiveStatusCard";
import { RingkasanTab } from "@/components/rapat/RingkasanTab";
import { styles } from "@/components/rapat/styles";
import { TranskripTab } from "@/components/rapat/TranskripTab";
import { useTranscriptEditor } from "@/hooks/useTranscriptEditor";
import { useAuth } from "@/lib/auth-context";

// Halaman detail satu rapat: memuat rapat, memantau statusnya selama masih direkam/diproses, lalu menampilkan header
// dan tiga tab. Isi tiap tab ada di components/rapat/.

// polling menyerah setelah sekian permintaan gagal berturut-turut. Permintaan gagal tidak memberi tahu apa-apa soal job-nya (gangguan,
// Docker lambat), hanya respons 200 dengan status "failed" yang memberi tahu, jadi ia mencoba lagi daripada membekukan halaman
const MAX_CONSECUTIVE_POLL_FAILURES = 10;
const LIVE_STATUSES = ["queued", "joining", "recording", "stopping", "processing"];

const TABS = [
  { key: "ringkasan", label: "Pokok Pembahasan Rapat", icon: "zap" },
  { key: "transkrip", label: "Transkrip", icon: "file-text" },
  { key: "edit", label: "Edit Transkrip", icon: "edit-3" },
];

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
  const [processBusy, setProcessBusy] = useState(false);
  const [processError, setProcessError] = useState("");
  const router = useRouter();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const editor = useTranscriptEditor(id, setMeeting);

  useEffect(() => () => clearTimeout(pollTimer.current), []);

  // meeting yang dimuat juga mengembalikan editor ke yang tersimpan
  function showMeeting(data) {
    setMeeting(data);
    editor.load(data);
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

  function handleToggleShareTeam() {
    const enabled = !meeting.shared_with_team;
    setSharingTeam(true);
    shareMeetingWithTeam(id, enabled)
      .then(() => setMeeting((m) => ({ ...m, shared_with_team: enabled })))
      .catch(() => {})
      .finally(() => setSharingTeam(false));
  }

  const stats = meetingStats(meeting || {});
  const canEdit = !!meeting?.can_edit; // penonton (tautan, team) hanya membaca, backend menolak ubahan mereka
  const isLive = liveStatus && liveStatus !== "failed";
  const isLiveFailed = liveStatus === "failed";

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
                {!isLive && user?.team_id && meeting.user_id === user.id && (
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
                {!isLive && canEdit && (
                  <Pressable
                    style={[styles.smallButton, !(user?.team_id && meeting.user_id === user?.id) && { marginLeft: "auto" }]}
                    onPress={() => setConfirmDelete(true)}
                  >
                    <Feather name="trash-2" size={12} color={colors.danger} />
                    <Text style={[styles.smallButtonLabel, { color: colors.danger }]}>Hapus Rapat</Text>
                  </Pressable>
                )}
                <ConfirmModal
                  visible={confirmDelete}
                  icon="trash-2"
                  title="Hapus rapat ini?"
                  body="Rapat beserta rekaman, transkrip, dan ringkasannya akan dihapus permanen dan tidak bisa dikembalikan."
                  error={deleteError}
                  confirmLabel="Ya, Hapus"
                  busy={deleting}
                  onCancel={() => setConfirmDelete(false)}
                  onConfirm={handleDeleteMeeting}
                />


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
            {isLive && <LiveStatusCard liveStatus={liveStatus} elapsed={elapsed} canEdit={canEdit} onStop={handleStop} />}

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

            {/* Pemrosesan gagal tapi rekamannya tersimpan: bisa diproses ulang (kuota paket dicek di server) */}
            {!isLive && !isLiveFailed && meeting.status === "failed" && !!meeting.recording && canEdit && (
              <View style={styles.liveCard}>
                <View style={styles.liveFailedRow}>
                  <Feather name="alert-circle" size={20} color={colors.danger} />
                  <Text style={[styles.summaryText, { flex: 1 }]}>
                    Pemrosesan rapat ini gagal, tetapi rekamannya masih tersimpan. Klik Proses Ulang untuk membuat
                    transkrip dan ringkasan lagi.
                  </Text>
                </View>
                <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: spacing.sm }}>
                  <Pressable style={styles.smallButton} onPress={handleProcessNow} disabled={processBusy}>
                    <Feather name="refresh-cw" size={12} color={colors.ink} />
                    <Text style={styles.smallButtonLabel}>{processBusy ? "Memulai..." : "Proses Ulang"}</Text>
                  </Pressable>
                  {!!processError && <Text style={styles.errorText}>{processError}</Text>}
                  {processError.includes("Upgrade") && (
                    <Pressable style={styles.kbButton} onPress={() => router.push("/billing")}>
                      <Feather name="zap" size={13} color={colors.ink} />
                      <Text style={styles.kbButtonLabel}>Upgrade ke Pro</Text>
                    </Pressable>
                  )}
                </View>
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
                  {TABS.filter((tab) => canEdit || tab.key !== "edit").map((tab) => {
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

                {activeTab === "ringkasan" && <RingkasanTab id={id} meeting={meeting} setMeeting={setMeeting} canEdit={canEdit} />}

                {activeTab === "transkrip" && (
                  <TranskripTab
                    meeting={meeting}
                    videoRef={videoRef}
                    currentTime={currentTime}
                    setCurrentTime={setCurrentTime}
                    seekTo={seekTo}
                  />
                )}

                {activeTab === "edit" && (
                  <EditorTab
                    meeting={meeting}
                    editor={editor}
                    videoRef={videoRef}
                    currentTime={currentTime}
                    setCurrentTime={setCurrentTime}
                    seekTo={seekTo}
                  />
                )}
              </>
            )}
          </>
        )}
      </View>
    </ScrollView>
  );
}
