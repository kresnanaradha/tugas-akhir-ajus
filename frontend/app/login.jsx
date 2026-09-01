import { Feather } from "@expo/vector-icons";
import { Link } from "expo-router";
import { useState } from "react";
import { Image, Pressable, StyleSheet, Text, TextInput, View, useWindowDimensions } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";

const PITCH_POINTS = [
  "Rekam rapat Google Meet & Zoom secara otomatis",
  "Transkripsi & ringkasan berbasis AI",
  "Knowledge Base semantik dari seluruh rapat",
  "Laporan & analitik penggunaan organisasi",
];

export default function LoginScreen() {
  const { width } = useWindowDimensions();
  const isWide = width >= 900;
  const [tab, setTab] = useState("masuk");

  return (
    <View style={[styles.screen, isWide && styles.screenWide]}>
      {isWide && (
        <View style={styles.pitch}>
          <View style={styles.ring1} />
          <View style={styles.ring2} />

          <View style={styles.brand}>
            <Image source={require("@/assets/images/logo.png")} style={styles.logo} resizeMode="contain" />
            <Text style={styles.brandLabel}>Notulis</Text>
          </View>

          <Text style={styles.headline}>Asisten Rapat{"\n"}Berbasis AI</Text>
          <Text style={styles.subheadline}>
            Rekam, transkripsi, dan ringkas rapat daring Anda secara otomatis.
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

          <View style={styles.quote}>
            <View style={styles.quoteAvatar}>
              <Text style={styles.quoteAvatarLabel}>DK</Text>
            </View>
            <View style={styles.quoteBody}>
              <Text style={styles.quoteText}>"Notulis menghemat 2 jam per minggu untuk tim kami."</Text>
              <Text style={styles.quoteAttribution}>Dewi Kartika · Head of Operations, PT Inovasi Digital</Text>
            </View>
          </View>
        </View>
      )}

      <View style={styles.formSide}>
        <View style={styles.formCard}>
          <View style={styles.tabRow}>
            <Pressable style={[styles.tabButton, tab === "masuk" && styles.tabButtonActive]} onPress={() => setTab("masuk")}>
              <Text style={[styles.tabLabel, tab === "masuk" && styles.tabLabelActive]}>Masuk</Text>
            </Pressable>
            <Pressable style={[styles.tabButton, tab === "daftar" && styles.tabButtonActive]} onPress={() => setTab("daftar")}>
              <Text style={[styles.tabLabel, tab === "daftar" && styles.tabLabelActive]}>Daftar</Text>
            </Pressable>
          </View>

          <Text style={styles.formTitle}>{tab === "masuk" ? "Selamat datang kembali" : "Buat akun organisasi"}</Text>
          <Text style={styles.formSubtitle}>
            {tab === "masuk" ? "Masuk ke akun Notulis Anda" : "Mulai kelola rapat organisasi Anda"}
          </Text>

          <View style={styles.field}>
            <Text style={styles.fieldLabel}>EMAIL</Text>
            <TextInput
              style={styles.input}
              placeholder="admin@ptmajubersama.co.id"
              placeholderTextColor={colors.inkFaint}
              autoCapitalize="none"
            />
          </View>

          <View style={styles.field}>
            <View style={styles.fieldLabelRow}>
              <Text style={styles.fieldLabel}>PASSWORD</Text>
              {tab === "masuk" && (
                <Pressable>
                  <Text style={styles.forgotLink}>Lupa password?</Text>
                </Pressable>
              )}
            </View>
            <TextInput style={styles.input} placeholder="••••••••" placeholderTextColor={colors.inkFaint} secureTextEntry />
          </View>

          <Link href="/dashboard" asChild>
            <Pressable style={styles.submit}>
              <Text style={styles.submitLabel}>{tab === "masuk" ? "Masuk" : "Daftar"}</Text>
            </Pressable>
          </Link>

          <Text style={styles.demoNote}>Demo: tekan tombol untuk lihat dashboard</Text>
        </View>
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
    justifyContent: "space-between",
    overflow: "hidden",
    position: "relative",
  },
  ring1: {
    position: "absolute",
    right: -60,
    top: -60,
    width: 220,
    height: 220,
    borderRadius: 110,
    borderWidth: 1,
    borderColor: "rgba(27,31,43,0.15)",
  },
  ring2: {
    position: "absolute",
    right: 40,
    top: 90,
    width: 110,
    height: 110,
    borderRadius: 55,
    backgroundColor: "rgba(27,31,43,0.08)",
  },
  brand: { flexDirection: "row", alignItems: "center", gap: 10 },
  logo: { width: 30, height: 30 },
  brandLabel: { ...type.h1, color: colors.ink },

  headline: { ...type.display, fontSize: 40, color: colors.ink, marginTop: spacing.xxl, lineHeight: 46 },
  subheadline: { ...type.body, fontSize: 16, color: colors.inkSoft, marginTop: spacing.md, maxWidth: 360 },

  pointList: { gap: spacing.md, marginTop: spacing.xxl },
  pointRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  pointCheck: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.ink,
    alignItems: "center",
    justifyContent: "center",
  },
  pointLabel: { ...type.body, color: colors.ink },

  quote: {
    flexDirection: "row",
    gap: spacing.md,
    backgroundColor: "rgba(255,255,255,0.35)",
    borderRadius: radius.md,
    padding: spacing.lg,
    marginTop: spacing.xxl,
    maxWidth: 420,
  },
  quoteAvatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.ink,
    alignItems: "center",
    justifyContent: "center",
  },
  quoteAvatarLabel: { color: colors.white, fontWeight: "700", fontSize: 12 },
  quoteBody: { flex: 1, gap: 4 },
  quoteText: { ...type.body, color: colors.ink, fontStyle: "italic" },
  quoteAttribution: { ...type.small, color: colors.goldDeep },

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
  demoNote: { ...type.small, color: colors.inkFaint, textAlign: "center", marginTop: spacing.md },
});
