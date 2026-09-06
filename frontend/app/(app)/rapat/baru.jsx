import { Feather } from "@expo/vector-icons";
import { Link, router } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";
import { startJoinMeeting } from "@/lib/api";
import { isValidMeetingUrl, MEETING_URL_HINTS } from "@/lib/validate";

const PLATFORMS = [
  { value: "google_meet", label: "Google Meet", icon: "video" },
  { value: "zoom", label: "Zoom", icon: "video" },
];

export default function BuatRapatScreen() {
  const [platform, setPlatform] = useState("google_meet");
  const [url, setUrl] = useState("");
  const [name, setName] = useState("Notulis Bot");
  const [numSpeakers, setNumSpeakers] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    setSubmitting(true);
    setError("");
    try {
      const { job_id } = await startJoinMeeting(
        platform,
        url.trim(),
        name.trim() || "Notulis Bot",
        numSpeakers ? Number(numSpeakers) : null
      );
      // The live join/record/process lifecycle from here on is shown on the
      // meeting detail page itself (it polls GET /jobs/<id> while the status
      // is joining/recording/stopping/processing), not inline here — so this
      // form's only job is to kick off the job and hand off to that page.
      router.replace(`/rapat/${job_id}`);
    } catch (e) {
      setError(e.message || "Terjadi kesalahan");
      setSubmitting(false);
    }
  }

  const trimmedUrl = url.trim();
  const urlLooksValid = trimmedUrl.length === 0 || isValidMeetingUrl(platform, trimmedUrl);
  const canSubmit = trimmedUrl.length > 0 && urlLooksValid && !submitting;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <Link href="/rapat" style={styles.backLink}>
          <Feather name="chevron-left" size={14} color={colors.inkSoft} /> Kembali ke Daftar Rapat
        </Link>

        <Text style={styles.title}>Buat Sesi Rapat Baru</Text>
        <Text style={styles.subtitle}>Bot Notulis akan bergabung dan merekam rapat Anda secara otomatis.</Text>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Informasi Rapat</Text>

          <Text style={styles.label}>PLATFORM</Text>
          <View style={styles.platformRow}>
            {PLATFORMS.map((p) => {
              const active = platform === p.value;
              return (
                <Pressable
                  key={p.value}
                  style={[styles.platformOption, active && styles.platformOptionActive]}
                  onPress={() => setPlatform(p.value)}
                  disabled={submitting}
                >
                  <Feather name={p.icon} size={14} color={active ? colors.ink : colors.inkSoft} />
                  <Text style={[styles.platformLabel, active && styles.platformLabelActive]}>{p.label}</Text>
                  {active && <Feather name="check" size={14} color={colors.goldDeep} style={{ marginLeft: "auto" }} />}
                </Pressable>
              );
            })}
          </View>

          <Text style={styles.label}>TAUTAN RAPAT *</Text>
          <TextInput
            style={[styles.input, !urlLooksValid && styles.inputInvalid]}
            placeholder={platform === "zoom" ? "https://zoom.us/j/xxx-xxxx-xxx" : "https://meet.google.com/xxx-xxxx-xxx"}
            placeholderTextColor={colors.inkFaint}
            value={url}
            onChangeText={setUrl}
            autoCapitalize="none"
            editable={!submitting}
          />
          {!urlLooksValid && <Text style={styles.errorText}>{MEETING_URL_HINTS[platform]}</Text>}

          <Text style={styles.label}>NAMA BOT</Text>
          <TextInput
            style={styles.input}
            value={name}
            onChangeText={setName}
            placeholderTextColor={colors.inkFaint}
            editable={!submitting}
          />

          <Text style={styles.label}>PERKIRAAN JUMLAH PESERTA (OPSIONAL)</Text>
          <TextInput
            style={styles.input}
            placeholder="mis. 4"
            placeholderTextColor={colors.inkFaint}
            value={numSpeakers}
            onChangeText={(v) => setNumSpeakers(v.replace(/[^0-9]/g, ""))}
            keyboardType="number-pad"
            editable={!submitting}
          />
          <Text style={styles.fieldHint}>
            Bukan angka pasti, cuma perkiraan buat bantu sistem membedakan label pembicara lebih akurat.
          </Text>

          <View style={styles.infoBox}>
            <Feather name="info" size={14} color={colors.goldDeep} />
            <Text style={styles.infoText}>
              Bot akan langsung bergabung begitu Anda menekan tombol di bawah. Anda akan diarahkan ke halaman rapat untuk
              melihat progres perekaman secara langsung.
            </Text>
          </View>

          {!!error && <Text style={styles.errorText}>{error}</Text>}

          <View style={styles.actions}>
            <Link href="/rapat" asChild>
              <Pressable style={styles.cancelButton}>
                <Text style={styles.cancelLabel}>Batal</Text>
              </Pressable>
            </Link>
            <Pressable style={[styles.submit, !canSubmit && styles.submitDisabled]} disabled={!canSubmit} onPress={run}>
              {submitting ? (
                <ActivityIndicator color={colors.ink} size="small" />
              ) : (
                <Feather name="video" size={14} color={colors.ink} />
              )}
              <Text style={styles.submitLabel}>Mulai & Rekam</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { alignItems: "center", padding: spacing.xxl },
  content: { gap: spacing.sm, maxWidth: 640, width: "100%" },

  backLink: { ...type.small, color: colors.inkSoft, marginBottom: spacing.md },
  title: { ...type.display, color: colors.ink },
  subtitle: { ...type.body, color: colors.inkSoft, marginBottom: spacing.lg },

  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.xl,
  },
  cardTitle: { ...type.h2, color: colors.ink, marginBottom: spacing.lg },

  label: { ...type.eyebrow, color: colors.inkFaint, marginTop: spacing.md, marginBottom: spacing.sm },
  platformRow: { flexDirection: "row", gap: spacing.sm },
  platformOption: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: 10,
    paddingHorizontal: spacing.md,
  },
  fieldHint: { ...type.small, color: colors.inkFaint, marginTop: 4 },
  platformOptionActive: { backgroundColor: colors.goldSoft, borderColor: colors.gold },
  platformLabel: { ...type.bodyMedium, color: colors.inkSoft },
  platformLabelActive: { color: colors.ink, fontWeight: "700" },
  input: {
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
  inputInvalid: { borderColor: colors.danger },

  infoBox: {
    flexDirection: "row",
    gap: 8,
    backgroundColor: colors.goldSoft,
    borderRadius: radius.sm,
    padding: spacing.md,
    marginTop: spacing.lg,
  },
  infoText: { ...type.small, color: colors.goldDeep, flex: 1, lineHeight: 17 },

  errorText: { ...type.small, color: colors.danger, marginTop: spacing.md },

  actions: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.xl },
  cancelButton: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: 11,
    paddingHorizontal: spacing.lg,
  },
  cancelLabel: { ...type.bodyMedium, color: colors.ink },
  submit: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    backgroundColor: colors.gold,
    borderRadius: radius.sm,
    paddingVertical: 11,
    paddingHorizontal: spacing.lg,
  },
  submitDisabled: { opacity: 0.4 },
  submitLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },
});
