import { Feather } from "@expo/vector-icons";
import { router } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, TextInput, View, useWindowDimensions } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";
import { forgotPassword, login, register } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

const PITCH_POINTS = [
  "Bot masuk otomatis ke Google Meet dan Zoom",
  "Transkrip lengkap dengan label pembicara",
  "Ringkasan, keputusan, dan action item dari AI",
  "Knowledge Base untuk mencari isi semua rapat",
];

const STEPS = [
  { icon: "link", title: "Tempel link", text: "Rapat Meet atau Zoom" },
  { icon: "mic", title: "Bot merekam", text: "Join dan rekam" },
  { icon: "file-text", title: "Terima hasil", text: "Transkrip dan ringkasan" },
];

export default function LoginScreen() {
  const { width } = useWindowDimensions();
  const isWide = width >= 900;
  const [tab, setTab] = useState("masuk");
  const { signIn } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [forgot, setForgot] = useState(false);
  const [sent, setSent] = useState(false);

  async function handleSubmit() {
    setError("");
    if (!email.trim() || !password) {
      setError("Email dan password wajib diisi.");
      return;
    }
    if (tab === "daftar" && !name.trim()) {
      setError("Nama wajib diisi.");
      return;
    }
    setSubmitting(true);
    try {
      const user = tab === "masuk" ? await login(email.trim(), password) : await register(email.trim(), password, name.trim());
      signIn(user);
      router.replace("/dashboard");
    } catch (e) {
      setError(e.message || "Terjadi kesalahan");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleForgot() {
    setError("");
    if (!email.trim()) {
      setError("Email wajib diisi.");
      return;
    }
    setSubmitting(true);
    try {
      await forgotPassword(email.trim());
      setSent(true);
    } catch (e) {
      setError(e.message || "Terjadi kesalahan");
    } finally {
      setSubmitting(false);
    }
  }

  function backToLogin() {
    setForgot(false);
    setSent(false);
    setError("");
  }

  return (
    <View style={[styles.screen, isWide && styles.screenWide]}>
      {isWide && (
        <View style={styles.pitch}>
          <View style={styles.ring1} />
          <View style={styles.ring2} />

          <View>
            <View style={styles.chip}>
              <Text style={styles.chipLabel}>ASISTEN RAPAT BERBASIS AI</Text>
            </View>
            <View style={styles.headlineBox}>
              <Text style={styles.headline}>Rapat selesai,</Text>
              <Text style={styles.headline}>
                catatan langsung jadi.
              </Text>
            </View>
            <Text style={styles.subheadline}>
              Notulis masuk ke rapat Anda, merekam, lalu menyusun transkrip dan ringkasan, tanpa perlu mencatat sendiri.
            </Text>

            <View style={styles.pointList}>
              {PITCH_POINTS.map((point) => (
                <View key={point} style={styles.pointRow}>
                  <View style={styles.pointCheck}>
                    <Feather name="check" size={11} color={colors.gold} />
                  </View>
                  <Text style={styles.pointLabel}>{point}</Text>
                </View>
              ))}
            </View>
          </View>

          <View style={styles.steps}>
            {STEPS.map((step, i) => (
              <View key={step.title} style={styles.step}>
                <View style={styles.stepIcon}>
                  <Feather name={step.icon} size={15} color={colors.gold} />
                </View>
                <Text style={styles.stepTitle}>
                  {i + 1}. {step.title}
                </Text>
                <Text style={styles.stepText}>{step.text}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      <View style={styles.formSide}>
        <View style={[styles.brand, { marginBottom: spacing.xl }]} accessibilityLabel="Notulis" accessible>
          <Image source={require("@/assets/images/logo.png")} style={styles.logo} resizeMode="contain" />
          <Text style={[styles.brandLabel, { color: colors.ink }]}>otulis</Text>
        </View>
        {forgot ? (
          <View style={styles.formCard}>
            <Text style={styles.formTitle}>Lupa password?</Text>
            <Text style={styles.formSubtitle}>
              {sent
                ? "Jika email terdaftar, tautan untuk mengatur ulang password sudah dikirim. Cek kotak masuk Anda (berlaku 1 jam)."
                : "Masukkan email akun Anda, kami kirim tautan untuk mengatur ulang password."}
            </Text>
            {!sent && (
              <>
                <View style={styles.field}>
                  <Text style={styles.fieldLabel}>EMAIL</Text>
                  <TextInput
                    style={styles.input}
                    placeholder="nama@perusahaan.com"
                    placeholderTextColor={colors.inkFaint}
                    autoCapitalize="none"
                    value={email}
                    onChangeText={setEmail}
                  />
                </View>
                {!!error && <Text style={styles.errorText}>{error}</Text>}
                <Pressable style={[styles.submit, submitting && styles.submitDisabled]} onPress={handleForgot} disabled={submitting}>
                  {submitting ? <ActivityIndicator color={colors.ink} size="small" /> : <Text style={styles.submitLabel}>Kirim Tautan Reset</Text>}
                </Pressable>
              </>
            )}
            <Pressable onPress={backToLogin} style={{ marginTop: spacing.lg, alignItems: "center" }}>
              <Text style={styles.forgotLink}>Kembali ke Masuk</Text>
            </Pressable>
          </View>
        ) : (
        <View style={styles.formCard}>
          <View style={styles.tabRow}>
            <Pressable style={[styles.tabButton, tab === "masuk" && styles.tabButtonActive]} onPress={() => setTab("masuk")}>
              <Text style={[styles.tabLabel, tab === "masuk" && styles.tabLabelActive]}>Masuk</Text>
            </Pressable>
            <Pressable style={[styles.tabButton, tab === "daftar" && styles.tabButtonActive]} onPress={() => setTab("daftar")}>
              <Text style={[styles.tabLabel, tab === "daftar" && styles.tabLabelActive]}>Daftar</Text>
            </Pressable>
          </View>

          <Text style={styles.formTitle}>{tab === "masuk" ? "Selamat datang kembali" : "Buat akun Notulis"}</Text>
          <Text style={styles.formSubtitle}>
            {tab === "masuk" ? "Masuk untuk melihat rapat dan ringkasan Anda" : "Mulai rekam dan ringkas rapat Anda"}
          </Text>

          {tab === "daftar" && (
            <View style={styles.field}>
              <Text style={styles.fieldLabel}>NAMA</Text>
              <TextInput
                style={styles.input}
                placeholder="Nama lengkap"
                placeholderTextColor={colors.inkFaint}
                value={name}
                onChangeText={setName}
              />
            </View>
          )}

          <View style={styles.field}>
            <Text style={styles.fieldLabel}>EMAIL</Text>
            <TextInput
              style={styles.input}
              placeholder="nama@perusahaan.com"
              placeholderTextColor={colors.inkFaint}
              autoCapitalize="none"
              value={email}
              onChangeText={setEmail}
            />
          </View>

          <View style={styles.field}>
            <View style={styles.fieldLabelRow}>
              <Text style={styles.fieldLabel}>PASSWORD</Text>
              {tab === "masuk" && (
                <Pressable onPress={() => setForgot(true)}>
                  <Text style={styles.forgotLink}>Lupa password?</Text>
                </Pressable>
              )}
            </View>
            <TextInput
              style={styles.input}
              placeholder="••••••••"
              placeholderTextColor={colors.inkFaint}
              secureTextEntry
              value={password}
              onChangeText={setPassword}
            />
          </View>

          {!!error && <Text style={styles.errorText}>{error}</Text>}

          <Pressable style={[styles.submit, submitting && styles.submitDisabled]} onPress={handleSubmit} disabled={submitting}>
            {submitting ? (
              <ActivityIndicator color={colors.ink} size="small" />
            ) : (
              <Text style={styles.submitLabel}>{tab === "masuk" ? "Masuk" : "Daftar"}</Text>
            )}
          </Pressable>
        </View>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface },
  screenWide: { flexDirection: "row" },

  pitch: {
    flex: 1,
    backgroundColor: colors.gold,
    padding: spacing.xxxl,
    justifyContent: "center",
    overflow: "hidden",
    position: "relative",
  },
  ring1: {
    position: "absolute",
    right: -80,
    top: -80,
    width: 280,
    height: 280,
    borderRadius: 140,
    borderWidth: 1,
    borderColor: "rgba(27,31,43,0.15)",
  },
  ring2: {
    position: "absolute",
    right: 50,
    top: 110,
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: "rgba(27,31,43,0.08)",
  },
  brand: { flexDirection: "row", alignItems: "center", gap: 2 },
  logo: { width: 44, height: 44 },
  brandLabel: { ...type.h1, fontSize: 22, color: colors.ink },

  chip: {
    alignSelf: "flex-start",
    borderWidth: 1,
    borderColor: "rgba(27,31,43,0.35)",
    borderRadius: radius.pill,
    paddingVertical: 5,
    paddingHorizontal: 12,
  },
  chipLabel: { ...type.small, fontSize: 11, fontWeight: "700", letterSpacing: 1.2, color: colors.ink },
  headlineBox: { marginTop: spacing.lg },
  headline: { ...type.display, fontSize: 52, lineHeight: 60, color: colors.ink },
  subheadline: { ...type.body, fontSize: 17, lineHeight: 26, color: colors.inkSoft, marginTop: spacing.lg, maxWidth: 480 },

  pointList: { gap: spacing.md, marginTop: spacing.xl + 4 },
  pointRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  pointCheck: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.ink,
    alignItems: "center",
    justifyContent: "center",
  },
  pointLabel: { ...type.body, color: colors.ink },

  steps: { flexDirection: "row", gap: spacing.md, marginTop: spacing.xxxl, maxWidth: 560 },
  step: {
    flex: 1,
    backgroundColor: "rgba(255,255,255,0.4)",
    borderWidth: 1,
    borderColor: "rgba(27,31,43,0.1)",
    borderRadius: radius.md,
    padding: spacing.md,
    gap: 4,
  },
  stepIcon: {
    width: 30,
    height: 30,
    borderRadius: 8,
    backgroundColor: colors.ink,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 4,
  },
  stepTitle: { ...type.small, fontWeight: "700", color: colors.ink },
  stepText: { ...type.small, color: colors.inkSoft },

  formSide: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xxl },
  formCard: { width: "100%", maxWidth: 340 },

  tabRow: {
    flexDirection: "row",
    backgroundColor: colors.surfaceSunken,
    borderRadius: radius.sm,
    padding: 3,
    marginBottom: spacing.xxl,
  },
  tabButton: { flex: 1, paddingVertical: 9, borderRadius: radius.sm - 2, alignItems: "center" },
  tabButtonActive: { backgroundColor: colors.surface },
  tabLabel: { ...type.bodyMedium, color: colors.inkFaint },
  tabLabelActive: { color: colors.ink, fontWeight: "700" },

  formTitle: { ...type.h1, color: colors.ink },
  formSubtitle: { ...type.body, color: colors.inkFaint, marginTop: 4, marginBottom: spacing.xl },

  field: { marginBottom: spacing.lg },
  fieldLabelRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  fieldLabel: { ...type.eyebrow, color: colors.inkFaint, marginBottom: spacing.sm },
  forgotLink: { ...type.small, color: colors.goldDeep, fontWeight: "600" },
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

  submit: {
    backgroundColor: colors.gold,
    borderRadius: radius.sm,
    paddingVertical: 13,
    alignItems: "center",
    marginTop: spacing.sm,
  },
  submitLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },
  errorText: { ...type.small, color: colors.danger, marginBottom: spacing.md },
  submitDisabled: { opacity: 0.6 },
});
