import { router, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { resetPassword } from "@/lib/api";

// Target of the link in the password-reset email (POST /auth/forgot). Public:
// lives outside (app)/ so a logged-out visitor isn't bounced to /login.
export default function ResetPasswordScreen() {
  const { token } = useLocalSearchParams();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit() {
    setError("");
    if (password.length < 8) return setError("Password minimal 8 karakter.");
    if (password !== confirm) return setError("Konfirmasi password tidak sama.");
    setSubmitting(true);
    try {
      await resetPassword(token, password);
      setDone(true);
      setTimeout(() => router.replace("/login"), 1800);
    } catch (e) {
      setError(e.message || "Terjadi kesalahan");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <View style={styles.screen}>
      <View style={styles.card}>
        <Text style={styles.title}>Atur Password Baru</Text>
        {done ? (
          <Text style={styles.subtitle}>Password berhasil diubah. Mengarahkan ke halaman masuk...</Text>
        ) : (
          <>
            <Text style={styles.subtitle}>Masukkan password baru untuk akun Anda.</Text>
            <Text style={styles.label}>PASSWORD BARU</Text>
            <TextInput style={styles.input} secureTextEntry value={password} onChangeText={setPassword} placeholder="Minimal 8 karakter" placeholderTextColor={colors.inkFaint} />
            <Text style={styles.label}>ULANGI PASSWORD</Text>
            <TextInput style={styles.input} secureTextEntry value={confirm} onChangeText={setConfirm} placeholderTextColor={colors.inkFaint} />
            {!!error && <Text style={styles.error}>{error}</Text>}
            <Pressable style={[styles.submit, submitting && { opacity: 0.6 }]} onPress={handleSubmit} disabled={submitting}>
              {submitting ? <ActivityIndicator color={colors.ink} size="small" /> : <Text style={styles.submitLabel}>Simpan Password</Text>}
            </Pressable>
          </>
        )}
        <Pressable onPress={() => router.replace("/login")} style={{ marginTop: spacing.lg, alignItems: "center" }}>
          <Text style={styles.link}>Kembali ke Masuk</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg, alignItems: "center", justifyContent: "center", padding: spacing.lg },
  card: { width: "100%", maxWidth: 420, backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.xl, ...shadow },
  title: { ...type.h1, color: colors.ink },
  subtitle: { ...type.body, color: colors.inkSoft, marginTop: spacing.xs, marginBottom: spacing.lg },
  label: { ...type.small, color: colors.inkSoft, fontWeight: "700", marginTop: spacing.md, marginBottom: spacing.xs },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, color: colors.ink, backgroundColor: colors.surface },
  error: { ...type.small, color: colors.danger, marginTop: spacing.md },
  submit: { backgroundColor: colors.gold, borderRadius: radius.md, paddingVertical: spacing.md, alignItems: "center", marginTop: spacing.lg },
  submitLabel: { ...type.body, color: colors.ink, fontWeight: "700" },
  link: { ...type.small, color: colors.goldDeep, fontWeight: "600" },
});
