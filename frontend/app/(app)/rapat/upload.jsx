import { Feather } from "@expo/vector-icons";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { listMeetings, uploadAudio } from "@/lib/api";
import { formatMeetingDate } from "@/lib/format";
import { usePipelineRun } from "@/hooks/usePipelineRun";
import { BackLink } from "@/components/BackLink";
import { PipelineResult } from "@/components/PipelineResult";
import { MeetingRow } from "@/components/MeetingRow";

// Mirrors UPLOAD_EXTENSIONS in meeting-bot/app.py.
const ACCEPTED = ".mp3,.wav,.m4a,.mp4,.webm,.ogg";

const FEATURES = [
  {
    icon: "zap",
    title: "Transkripsi Otomatis",
    body: "Audio ditranskripsi otomatis dengan speaker label, memakai Whisper.",
  },
  {
    icon: "file-text",
    title: "Ringkasan AI Otomatis",
    body: "Ringkasan eksekutif, keputusan, dan topik pembahasan dibuat otomatis oleh GPT-4o mini.",
  },
];

export default function UploadRapatScreen() {
  const [file, setFile] = useState(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [numSpeakers, setNumSpeakers] = useState("");
  const inputRef = useRef(null);
  const { status, result, error, run, reset } = usePipelineRun(() =>
    uploadAudio(file, numSpeakers ? Number(numSpeakers) : null)
  );

  const [recent, setRecent] = useState(null); // null = loading
  useEffect(() => {
    listMeetings()
      .then((data) => setRecent(data.slice(0, 4).map((m) => ({ ...m, ...formatMeetingDate(m.created_at) }))))
      .catch(() => setRecent([]));
  }, []);

  function handleFiles(fileList) {
    const picked = fileList?.[0];
    if (picked) setFile(picked);
  }

  function handleDone() {
    reset();
    setFile(null);
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <BackLink />

        <Text style={styles.title}>Upload Rapat</Text>
        <Text style={styles.subtitle}>Upload rekaman rapat untuk ditranskripsi dan diringkas otomatis oleh AI.</Text>

        {status === "done" && result ? (
          <View style={styles.card}>
            <PipelineResult result={result} onDone={handleDone} />
          </View>
        ) : status === "loading" ? (
          <View style={[styles.card, styles.loadingBox]}>
            <ActivityIndicator color={colors.gold} size="large" />
            <Text style={styles.loadingText}>
              Memproses transkripsi & ringkasan... bisa beberapa menit tergantung durasi file.
            </Text>
          </View>
        ) : (
          <View style={styles.split}>
            <View style={styles.mainCol}>
              {/* Raw DOM element (not RN View) so real drag-and-drop events work — this app targets web only. */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragOver(true);
                }}
                onDragLeave={() => setIsDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setIsDragOver(false);
                  handleFiles(e.dataTransfer.files);
                }}
                onClick={() => inputRef.current?.click()}
                style={{
                  border: `2px dashed ${isDragOver ? colors.gold : colors.border}`,
                  borderRadius: radius.md,
                  padding: 48,
                  textAlign: "center",
                  cursor: "pointer",
                  backgroundColor: isDragOver ? colors.goldSoft : colors.surfaceSunken,
                }}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept={ACCEPTED}
                  onChange={(e) => handleFiles(e.target.files)}
                  style={{ display: "none" }}
                />
                {/* Wrapped in one RN View so children lay out as a column — a
                    plain <div> gives RN <Text> siblings no block context, so
                    without this they render inline (all on one line). */}
                <View style={styles.dropInner}>
                  <View style={styles.dropIconWrap}>
                    <Feather name="upload" size={22} color={colors.goldDeep} />
                  </View>
                  <Text style={styles.dropTitle}>{file ? file.name : "Drag & drop file audio"}</Text>
                  <Text style={styles.dropNote}>{file ? "Klik untuk ganti file" : "atau klik untuk memilih file"}</Text>
                  <Text style={styles.dropFormats}>Format: MP3, WAV, M4A, OGG, WEBM, MP4</Text>
                </View>
              </div>

              {status === "error" && <Text style={styles.errorText}>{error}</Text>}

              {file && (
                <>
                  <Text style={styles.label}>PERKIRAAN JUMLAH PESERTA (OPSIONAL)</Text>
                  <TextInput
                    style={styles.numberInput}
                    placeholder="mis. 4"
                    placeholderTextColor={colors.inkFaint}
                    value={numSpeakers}
                    onChangeText={(v) => setNumSpeakers(v.replace(/[^0-9]/g, ""))}
                    keyboardType="number-pad"
                  />
                  <Text style={styles.fieldHint}>
                    Bukan angka pasti, cuma perkiraan buat bantu sistem membedakan label pembicara lebih akurat. Isi 1
                    kalau hanya ada satu pembicara: pemrosesan jauh lebih cepat, tapi semua ucapan diberi satu label.
                  </Text>

                  <Pressable style={styles.submit} onPress={run}>
                    <Feather name="zap" size={14} color={colors.ink} />
                    <Text style={styles.submitLabel}>Transkripsi & Ringkas</Text>
                  </Pressable>
                </>
              )}
            </View>

            <View style={styles.sideCol}>
              <View style={styles.sideCard}>
                {FEATURES.map((f) => (
                  <View key={f.title} style={styles.featureRow}>
                    <View style={styles.featureIcon}>
                      <Feather name={f.icon} size={14} color={colors.goldDeep} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.featureTitle}>{f.title}</Text>
                      <Text style={styles.featureBody}>{f.body}</Text>
                    </View>
                  </View>
                ))}
              </View>

              <View style={styles.sideCard}>
                <Text style={styles.sideTitle}>Rapat Terbaru</Text>
                {recent === null && <ActivityIndicator color={colors.gold} />}
                {recent?.length === 0 && <Text style={styles.featureBody}>Belum ada rapat.</Text>}
                {recent?.map((m) => (
                  <MeetingRow key={m.id} meeting={m} />
                ))}
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
  scrollContent: { alignItems: "center", padding: spacing.lg },
  content: { gap: spacing.md, maxWidth: 1200, width: "100%" },

  backLink: { ...type.small, color: colors.inkSoft, marginBottom: spacing.md },
  title: { ...type.h1, fontSize: 24, color: colors.ink },
  subtitle: { ...type.body, color: colors.inkSoft, marginBottom: spacing.lg },

  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
  },

  split: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, alignItems: "flex-start" },
  mainCol: { flex: 1.3, minWidth: 380, gap: spacing.sm },
  sideCol: { flex: 1, minWidth: 300, gap: spacing.md },
  sideCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
    gap: spacing.sm,
    ...shadow.card,
  },
  sideTitle: { ...type.bodyMedium, fontWeight: "700", color: colors.ink, marginBottom: 4 },

  dropInner: { alignItems: "center" },
  dropIconWrap: {
    width: 44,
    height: 44,
    borderRadius: radius.sm,
    backgroundColor: colors.goldSoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  dropTitle: { ...type.bodyMedium, fontWeight: "700", color: colors.ink, textAlign: "center" },
  dropNote: { ...type.small, color: colors.inkFaint, textAlign: "center", marginTop: 2 },
  dropFormats: { ...type.small, color: colors.inkFaint, textAlign: "center", marginTop: spacing.sm },

  errorText: { ...type.small, color: colors.danger },

  label: { ...type.eyebrow, color: colors.inkFaint, marginTop: spacing.md, marginBottom: spacing.sm },
  numberInput: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceSunken,
    paddingHorizontal: spacing.md,
    paddingVertical: 11,
    ...type.body,
    color: colors.ink,
    outlineStyle: "none",
  },
  fieldHint: { ...type.small, color: colors.inkFaint, marginTop: 4, marginBottom: spacing.sm },

  submit: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    backgroundColor: colors.gold,
    borderRadius: radius.sm,
    paddingVertical: 12,
  },
  submitLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },

  featureRow: { flexDirection: "row", gap: spacing.sm },
  featureIcon: {
    width: 26,
    height: 26,
    borderRadius: radius.sm,
    backgroundColor: colors.goldSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  featureTitle: { ...type.small, fontWeight: "700", color: colors.ink },
  featureBody: { ...type.small, color: colors.inkFaint, lineHeight: 16 },

  loadingBox: { alignItems: "center", gap: spacing.md },
  loadingText: { ...type.body, color: colors.inkSoft, textAlign: "center" },
});
