import { Feather } from "@expo/vector-icons";
import { Link } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";
import { getBillingStatus } from "@/lib/api";

const PLAN_LABEL = { free: "Free", pro: "Pro", team: "Team" };
// Webhook delivery and this redirect land at roughly the same time (both
// fire right after the user finishes on Xendit's page) — there's no
// guarantee the webhook has already updated our DB by the time this page
// loads, so poll briefly instead of trusting a single fetch.
const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 15000;

export default function CheckoutSuksesScreen() {
  const [subscription, setSubscription] = useState(null);
  const [timedOut, setTimedOut] = useState(false);
  const pollTimer = useRef(null);
  const deadlineRef = useRef(Date.now() + POLL_TIMEOUT_MS);

  useEffect(() => {
    function poll() {
      getBillingStatus()
        .then((data) => {
          setSubscription(data);
          if (data.status === "active") return; // done — plan confirmed
          if (Date.now() >= deadlineRef.current) {
            setTimedOut(true);
            return;
          }
          pollTimer.current = setTimeout(poll, POLL_INTERVAL_MS);
        })
        .catch(() => {
          if (Date.now() >= deadlineRef.current) {
            setTimedOut(true);
            return;
          }
          pollTimer.current = setTimeout(poll, POLL_INTERVAL_MS);
        });
    }
    poll();
    return () => clearTimeout(pollTimer.current);
  }, []);

  const confirmed = subscription?.status === "active";

  return (
    <View style={styles.screen}>
      <View style={styles.card}>
        {confirmed ? (
          <>
            <View style={styles.iconWrapSuccess}>
              <Feather name="check" size={28} color={colors.success} />
            </View>
            <Text style={styles.title}>Pembayaran Berhasil</Text>
            <Text style={styles.body}>
              Paket <Text style={styles.bold}>{PLAN_LABEL[subscription.plan] || subscription.plan}</Text> Anda sudah
              aktif. Tagihan berikutnya otomatis lewat metode bayar yang barusan Anda hubungkan.
            </Text>
          </>
        ) : timedOut ? (
          <>
            <View style={styles.iconWrapWarning}>
              <Feather name="clock" size={28} color={colors.goldDeep} />
            </View>
            <Text style={styles.title}>Masih Diproses</Text>
            <Text style={styles.body}>
              Xendit sudah menerima pembayaran Anda, tapi konfirmasinya belum sampai ke sistem kami. Coba muat ulang
              halaman Pengaturan sebentar lagi.
            </Text>
          </>
        ) : (
          <>
            <ActivityIndicator size="large" color={colors.gold} style={{ marginBottom: spacing.sm }} />
            <Text style={styles.title}>Mengonfirmasi Pembayaran...</Text>
            <Text style={styles.body}>Menunggu konfirmasi dari Xendit, biasanya cuma beberapa detik.</Text>
          </>
        )}

        <Link href="/pengaturan" asChild>
          <View style={styles.button}>
            <Text style={styles.buttonLabel}>Kembali ke Pengaturan</Text>
          </View>
        </Link>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xxl },
  card: {
    maxWidth: 420,
    width: "100%",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.xxl,
    alignItems: "center",
    gap: spacing.sm,
  },
  iconWrapSuccess: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.successSoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  iconWrapWarning: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.goldSoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  title: { ...type.h1, color: colors.ink, textAlign: "center" },
  body: { ...type.body, color: colors.inkSoft, textAlign: "center", lineHeight: 20 },
  bold: { fontWeight: "700", color: colors.ink },
  button: {
    marginTop: spacing.lg,
    backgroundColor: colors.gold,
    borderRadius: radius.sm,
    paddingVertical: 11,
    paddingHorizontal: spacing.xl,
  },
  buttonLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },
});
