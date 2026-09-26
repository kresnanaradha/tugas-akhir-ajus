import { Feather } from "@expo/vector-icons";
import { useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";
import { cancelSubscription, getBillingStatus, startCheckout } from "@/lib/api";

// Illustrative pricing/quotas — not backed by a real business decision, just
// what the checkout call actually charges (PLAN_PRICES in app.py) so the
// numbers shown here and what Xendit charges don't drift apart.
const PLANS = [
  {
    key: "free",
    name: "Free",
    price: "Rp0",
    billing: "selamanya",
    tagline: "Buat coba-coba sendirian.",
    features: ["5 rapat direkam / bulan", "Transkripsi & ringkasan AI otomatis", "1 pengguna"],
  },
  {
    key: "pro",
    name: "Pro",
    price: "Rp99rb",
    billing: "/ bulan / pengguna",
    tagline: "Buat individu yang rutin rapat.",
    features: [
      "Rapat direkam tanpa batas",
      "Video + transkrip tersinkron, editor transkrip",
      "Knowledge Base pencarian semantik",
      "1 pengguna",
    ],
    highlighted: true,
  },
  {
    key: "team",
    name: "Team",
    price: "Rp299rb",
    billing: "/ bulan, mulai 3 pengguna",
    tagline: "Buat tim yang berbagi hasil rapat.",
    features: ["Semua fitur Pro", "Multi-pengguna dengan peran Admin & Member", "Laporan aktivitas tim"],
  },
];

const STATUS_LABEL = {
  active: null, // nothing extra to say — the plan badge already covers it
  pending: "Menunggu konfirmasi pembayaran...",
  past_due: "Pembayaran terakhir gagal — coba perbarui metode bayar Anda.",
  canceled: null,
};

export default function PengaturanScreen() {
  const { checkout } = useLocalSearchParams();
  const [subscription, setSubscription] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [pendingPlan, setPendingPlan] = useState(null); // which plan's button is mid-click
  const [actionError, setActionError] = useState("");
  const [confirmDowngradeOpen, setConfirmDowngradeOpen] = useState(false);

  function loadStatus() {
    getBillingStatus()
      .then(setSubscription)
      .catch((e) => setLoadError(e.message || "Gagal memuat status langganan"));
  }

  useEffect(() => {
    loadStatus();
  }, []);

  async function handleUpgrade(plan) {
    setPendingPlan(plan);
    setActionError("");
    try {
      const { checkout_url } = await startCheckout(plan);
      window.location.href = checkout_url; // hand off to Xendit's hosted checkout page
    } catch (e) {
      setActionError(e.message || "Gagal memulai checkout");
      setPendingPlan(null);
    }
  }

  async function handleCancel() {
    setConfirmDowngradeOpen(false);
    setPendingPlan("cancel");
    setActionError("");
    try {
      const fresh = await cancelSubscription();
      setSubscription(fresh);
    } catch (e) {
      setActionError(e.message || "Gagal membatalkan langganan");
    } finally {
      setPendingPlan(null);
    }
  }

  // Only an "active" subscription actually counts as being on that plan —
  // "pending" means checkout was started but never confirmed by the webhook
  // yet, so it shouldn't show as upgraded (or block re-clicking Upgrade)
  // until the payment genuinely goes through.
  const currentPlan = subscription?.status === "active" ? subscription.plan : "free";
  const statusNote = subscription ? STATUS_LABEL[subscription.status] : null;
  // Billing already stopped (Xendit's recurring plan was deactivated the
  // moment this was scheduled) — this is purely "you keep access until...".
  const scheduledCancel = subscription?.status === "active" && subscription?.cancel_at_period_end;
  const periodEndLabel =
    scheduledCancel && subscription.current_period_end
      ? new Intl.DateTimeFormat("id-ID", { day: "numeric", month: "long", year: "numeric" }).format(
          new Date(subscription.current_period_end)
        )
      : null;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <Text style={styles.eyebrow}>MENU</Text>
        <Text style={styles.title}>Pengaturan</Text>
        <Text style={styles.description}>Paket langganan dan preferensi akun.</Text>

        {checkout === "cancel" && (
          <View style={styles.noticeBox}>
            <Feather name="info" size={14} color={colors.inkFaint} />
            <Text style={styles.noticeText}>Checkout dibatalkan, paket tidak berubah.</Text>
          </View>
        )}

        <Text style={styles.sectionTitle}>Paket Langganan</Text>
        {!!loadError && <Text style={styles.errorText}>{loadError}</Text>}
        {!!statusNote && (
          <View style={[styles.noticeBox, subscription.status === "past_due" && styles.noticeBoxWarning]}>
            <Feather
              name={subscription.status === "past_due" ? "alert-circle" : "clock"}
              size={14}
              color={subscription.status === "past_due" ? colors.danger : colors.inkFaint}
            />
            <Text style={styles.noticeText}>{statusNote}</Text>
          </View>
        )}
        {scheduledCancel && (
          <View style={styles.noticeBox}>
            <Feather name="calendar" size={14} color={colors.inkFaint} />
            <Text style={styles.noticeText}>
              Langganan gak diperpanjang lagi — tetap bisa pakai paket {PLANS.find((p) => p.key === currentPlan)?.name}{" "}
              sampai <Text style={{ fontWeight: "700" }}>{periodEndLabel}</Text>, baru abis itu turun ke Free.
            </Text>
          </View>
        )}

        <View style={styles.planRow}>
          {PLANS.map((plan) => {
            const isCurrent = plan.key === currentPlan;
            const isLoadingThis = pendingPlan === plan.key;
            return (
              <View key={plan.key} style={[styles.planCard, plan.highlighted && styles.planCardHighlighted]}>
                {plan.highlighted && (
                  <View style={styles.popularBadge}>
                    <Text style={styles.popularBadgeLabel}>Paling Populer</Text>
                  </View>
                )}
                <Text style={styles.planName}>{plan.name}</Text>
                <Text style={styles.planTagline}>{plan.tagline}</Text>

                <View style={styles.priceRow}>
                  <Text style={styles.price}>{plan.price}</Text>
                  <Text style={styles.priceBilling}>{plan.billing}</Text>
                </View>

                <View style={styles.featureList}>
                  {plan.features.map((feature) => (
                    <View key={feature} style={styles.featureRow}>
                      <Feather name="check" size={14} color={colors.success} />
                      <Text style={styles.featureLabel}>{feature}</Text>
                    </View>
                  ))}
                </View>

                {plan.key === "free" ? (
                  <Pressable
                    style={[styles.planButton, (isCurrent || scheduledCancel) && styles.planButtonCurrent]}
                    disabled={isCurrent || scheduledCancel || pendingPlan === "cancel"}
                    onPress={() => setConfirmDowngradeOpen(true)}
                  >
                    {pendingPlan === "cancel" ? (
                      <ActivityIndicator size="small" color={colors.inkFaint} />
                    ) : (
                      <Text style={[styles.planButtonLabel, (isCurrent || scheduledCancel) && styles.planButtonLabelCurrent]}>
                        {isCurrent ? "Paket Saat Ini" : scheduledCancel ? "Dijadwalkan Turun" : "Turunkan ke Free"}
                      </Text>
                    )}
                  </Pressable>
                ) : (
                  <Pressable
                    style={[
                      styles.planButton,
                      plan.highlighted && styles.planButtonHighlighted,
                      isCurrent && styles.planButtonCurrent,
                    ]}
                    disabled={isCurrent || !!pendingPlan}
                    onPress={() => handleUpgrade(plan.key)}
                  >
                    {isLoadingThis ? (
                      <ActivityIndicator size="small" color={colors.ink} />
                    ) : (
                      <Text
                        style={[
                          styles.planButtonLabel,
                          plan.highlighted && styles.planButtonLabelHighlighted,
                          isCurrent && styles.planButtonLabelCurrent,
                        ]}
                      >
                        {isCurrent ? "Paket Saat Ini" : `Upgrade ke ${plan.name}`}
                      </Text>
                    )}
                  </Pressable>
                )}
              </View>
            );
          })}
        </View>
        {!!actionError && <Text style={styles.errorText}>{actionError}</Text>}

        <View style={styles.membersCard}>
          <View style={styles.membersHeader}>
            <View style={styles.iconWrap}>
              <Feather name="credit-card" size={20} color={colors.goldDeep} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.membersTitle}>Pembayaran</Text>
              <Text style={styles.membersBody}>
                Diproses lewat Xendit (mode subscription/recurring) upgrade mengarahkan Anda ke halaman pembayaran
                Xendit buat menghubungkan metode bayar, lalu auto-charge tiap bulan. Riwayat pembayaran & unduhan
                invoice belum ada di sini.
              </Text>
            </View>
          </View>
        </View>
      </View>

      <Modal visible={confirmDowngradeOpen} transparent animationType="fade" onRequestClose={() => setConfirmDowngradeOpen(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <View style={styles.modalIconWrap}>
              <Feather name="alert-triangle" size={20} color={colors.danger} />
            </View>
            <Text style={styles.modalTitle}>Turunkan ke Free?</Text>
            <Text style={styles.modalBody}>
              Langganan gak akan diperpanjang lagi, tapi Anda tetap bisa pakai paket ini sampai periode yang sudah dibayar
              habis bukan langsung berhenti sekarang.
            </Text>
            <View style={styles.modalActions}>
              <Pressable style={styles.modalCancelButton} onPress={() => setConfirmDowngradeOpen(false)}>
                <Text style={styles.modalCancelLabel}>Batal</Text>
              </Pressable>
              <Pressable style={styles.modalConfirmButton} onPress={handleCancel}>
                <Text style={styles.modalConfirmLabel}>Ya, Turunkan</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { alignItems: "center", padding: spacing.lg },
  content: { gap: spacing.sm, maxWidth: 960, width: "100%" },
  eyebrow: { ...type.eyebrow, color: colors.inkFaint },
  title: { ...type.h1, fontSize: 24, color: colors.ink, marginTop: 4 },
  description: { ...type.body, color: colors.inkSoft, marginTop: 2, marginBottom: spacing.lg },
  sectionTitle: { ...type.h2, color: colors.ink, marginBottom: spacing.sm },
  errorText: { ...type.small, color: colors.danger, marginBottom: spacing.sm },

  noticeBox: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: colors.surfaceSunken,
    borderRadius: radius.sm,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  noticeBoxWarning: { backgroundColor: colors.dangerSoft },
  noticeText: { ...type.small, color: colors.inkSoft, flex: 1 },

  planRow: { flexDirection: "row", gap: spacing.lg, alignItems: "stretch" },
  planCard: {
    flex: 1,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
    gap: spacing.md,
    position: "relative",
  },
  planCardHighlighted: { borderColor: colors.gold, borderWidth: 2 },
  popularBadge: {
    position: "absolute",
    top: -12,
    left: spacing.xl,
    backgroundColor: colors.gold,
    borderRadius: radius.pill,
    paddingVertical: 3,
    paddingHorizontal: 10,
  },
  popularBadgeLabel: { ...type.small, fontWeight: "700", color: colors.ink },

  planName: { ...type.h1, color: colors.ink },
  planTagline: { ...type.small, color: colors.inkFaint, marginTop: -8 },

  priceRow: { flexDirection: "row", alignItems: "baseline", gap: 6 },
  price: { ...type.display, fontSize: 26, color: colors.ink },
  priceBilling: { ...type.small, color: colors.inkFaint },

  featureList: { gap: spacing.sm, flex: 1 },
  featureRow: { flexDirection: "row", alignItems: "flex-start", gap: 8 },
  featureLabel: { ...type.body, color: colors.inkSoft, flex: 1, lineHeight: 19 },

  planButton: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: 11,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 42,
  },
  planButtonHighlighted: { backgroundColor: colors.gold, borderColor: colors.gold },
  planButtonCurrent: { backgroundColor: colors.surfaceSunken },
  planButtonLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },
  planButtonLabelHighlighted: { color: colors.ink },
  planButtonLabelCurrent: { color: colors.inkFaint },

  membersCard: {
    marginTop: spacing.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
  },
  membersHeader: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start" },
  iconWrap: {
    width: 44,
    height: 44,
    borderRadius: radius.sm,
    backgroundColor: colors.goldSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  membersTitle: { ...type.h2, color: colors.ink, marginBottom: 4 },
  membersBody: { ...type.body, color: colors.inkFaint, lineHeight: 20 },

  modalOverlay: {
    flex: 1,
    backgroundColor: "rgba(27,31,43,0.45)",
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.lg,
  },
  modalCard: {
    maxWidth: 360,
    width: "100%",
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.lg,
    alignItems: "center",
    gap: spacing.sm,
  },
  modalIconWrap: {
    width: 44,
    height: 44,
    borderRadius: radius.sm,
    backgroundColor: colors.dangerSoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xs,
  },
  modalTitle: { ...type.h2, color: colors.ink, textAlign: "center" },
  modalBody: { ...type.body, color: colors.inkSoft, textAlign: "center", lineHeight: 19 },
  modalActions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, alignSelf: "stretch" },
  modalCancelButton: {
    flex: 1,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: 11,
    alignItems: "center",
  },
  modalCancelLabel: { ...type.bodyMedium, fontWeight: "600", color: colors.ink },
  modalConfirmButton: {
    flex: 1,
    backgroundColor: colors.danger,
    borderRadius: radius.sm,
    paddingVertical: 11,
    alignItems: "center",
  },
  modalConfirmLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.white },
});
