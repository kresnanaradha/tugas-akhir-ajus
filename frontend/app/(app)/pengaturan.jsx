import { Feather } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import {
  cancelPendingCheckout,
  cancelSubscription,
  changePassword,
  deactivateAccount,
  getBillingStatus,
  logout as apiLogout,
  startCheckout,
  updateProfile,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { initialsOf } from "@/lib/format";

// Illustrative pricing/quotas — not backed by a real business decision, just
// what the checkout call actually charges (PLAN_PRICES in app.py) so the
// numbers shown here and what Xendit charges don't drift apart. Limits
// (meetings/month, recording minutes/week) mirror billing_store.PLAN_LIMITS, the
// actual enforced source of truth — keep the two in sync if either changes.
const PLANS = [
  {
    key: "free",
    name: "Free",
    icon: "user",
    price: "Rp0",
    billing: "selamanya",
    tagline: "Untuk eksplorasi sendiri.",
    features: [
      "Maks. 5 rapat / bulan",
      "60 menit rekaman / minggu",
      "Transkripsi & ringkasan AI otomatis",
      "1 pengguna",
    ],
  },
  {
    key: "pro",
    name: "Pro",
    icon: "zap",
    price: "Rp99rb",
    billing: "/ bulan / pengguna",
    tagline: "Untuk individu yang rutin rapat.",
    features: [
      "Rapat & durasi rekaman tanpa batas",
      "Video + transkrip tersinkron, editor transkrip",
      "Knowledge Base pencarian semantik",
      "1 pengguna",
    ],
    highlighted: true,
  },
  {
    key: "team",
    name: "Team",
    icon: "users",
    price: "Rp299rb",
    billing: "/ bulan, mulai 3 pengguna",
    tagline: "Untuk tim yang berbagi hasil rapat.",
    features: ["Semua fitur Pro", "Multi-pengguna, peran Admin & Member", "Laporan aktivitas tim"],
  },
];

const STATUS_LABEL = {
  active: null, // nothing extra to say — the plan badge already covers it
  pending: "Menunggu konfirmasi pembayaran...",
  past_due: "Pembayaran terakhir gagal — coba perbarui metode bayar Anda.",
  canceled: null,
};

// One text field with its own Save button and saved/error feedback — used
// for Nama/Email/Nomor Telepon below, otherwise identical in shape.
// Assumes `initialValue` is already loaded by mount time (true here: the
// (app)/ layout only renders its children once useAuth()'s user exists).
// allowEmpty: Nama/Email may never be blank, but an optional field like
// phone should be clearable back to "" (so it can't just check value.trim()
// is truthy the way the required fields do).
function EditableField({ label, initialValue, keyboardType, allowEmpty, onSave }) {
  const [value, setValue] = useState(initialValue);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const changed = (allowEmpty || value.trim()) && value.trim() !== initialValue;

  async function handleSave() {
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      await onSave(value.trim());
      setSaved(true);
    } catch (e) {
      setError(e.message || "Gagal menyimpan");
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={styles.profileField}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={styles.fieldRow}>
        <TextInput
          style={styles.fieldInput}
          value={value}
          onChangeText={(v) => {
            setValue(v);
            setSaved(false);
          }}
          autoCapitalize={keyboardType === "email-address" ? "none" : "sentences"}
          keyboardType={keyboardType}
          placeholderTextColor={colors.inkFaint}
        />
        <Pressable
          style={[styles.smallButton, !changed && styles.smallButtonDisabled]}
          disabled={!changed || saving}
          onPress={handleSave}
        >
          {saving ? <ActivityIndicator size="small" color={colors.ink} /> : <Text style={styles.smallButtonLabel}>Simpan</Text>}
        </Pressable>
      </View>
      {!!error && <Text style={styles.errorText}>{error}</Text>}
      {saved && <Text style={styles.savedText}>Tersimpan.</Text>}
    </View>
  );
}

function ProfileCard() {
  const { user, updateUser, signOut } = useAuth();

  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [savingPassword, setSavingPassword] = useState(false);
  const [passwordError, setPasswordError] = useState("");
  const [passwordSaved, setPasswordSaved] = useState(false);

  const [savingNotif, setSavingNotif] = useState(false);
  const [confirmDeactivateOpen, setConfirmDeactivateOpen] = useState(false);
  const [deactivating, setDeactivating] = useState(false);
  const [deactivateError, setDeactivateError] = useState("");

  function handleLogout() {
    apiLogout().catch(() => {});
    signOut();
    router.replace("/login");
  }

  async function handleToggleNotif(value) {
    setSavingNotif(true);
    try {
      const fresh = await updateProfile({ email_notifications: value });
      updateUser(fresh);
    } catch {
      // Best-effort — the switch just stays at its current (unsaved) value
      // if this fails, no separate error banner for one toggle.
    } finally {
      setSavingNotif(false);
    }
  }

  async function handleDeactivate() {
    setDeactivating(true);
    setDeactivateError("");
    try {
      await deactivateAccount();
      signOut();
      router.replace("/login");
    } catch (e) {
      setDeactivateError(e.message || "Gagal menonaktifkan akun");
      setDeactivating(false);
    }
  }

  async function handleChangePassword() {
    setPasswordError("");
    setPasswordSaved(false);
    if (newPassword !== confirmPassword) {
      setPasswordError("Konfirmasi password baru tidak cocok");
      return;
    }
    setSavingPassword(true);
    try {
      await changePassword(currentPassword, newPassword);
      setPasswordSaved(true);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setShowPasswordForm(false);
    } catch (e) {
      setPasswordError(e.message || "Gagal mengubah password");
    } finally {
      setSavingPassword(false);
    }
  }

  return (
    <View style={styles.profileCard}>
      <View style={styles.profileHeader}>
        <View style={styles.avatar}>
          <Text style={styles.avatarLabel}>{initialsOf(user?.name)}</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.profileName}>{user?.name}</Text>
          <Text style={styles.profileEmail}>{user?.email}</Text>
        </View>
        <View style={styles.roleBadge}>
          <Text style={styles.roleBadgeLabel}>{user?.role === "super_admin" ? "Super Admin" : "User"}</Text>
        </View>
      </View>

      <EditableField
        label="NAMA"
        initialValue={user?.name || ""}
        onSave={(name) => updateProfile({ name }).then(updateUser)}
      />

      <View style={styles.divider} />

      <EditableField
        label="EMAIL"
        initialValue={user?.email || ""}
        keyboardType="email-address"
        onSave={(email) => updateProfile({ email }).then(updateUser)}
      />

      <View style={styles.divider} />

      <EditableField
        label="NOMOR TELEPON"
        initialValue={user?.phone || ""}
        keyboardType="phone-pad"
        allowEmpty
        onSave={(phone) => updateProfile({ phone }).then(updateUser)}
      />

      <View style={styles.divider} />

      <View style={styles.profileField}>
        <View style={styles.fieldRow}>
          <Text style={styles.fieldLabel}>PASSWORD</Text>
          {!showPasswordForm && (
            <Pressable onPress={() => setShowPasswordForm(true)} hitSlop={6}>
              <Text style={styles.link}>Ubah Password</Text>
            </Pressable>
          )}
        </View>

        {!showPasswordForm && passwordSaved && <Text style={styles.savedText}>Password berhasil diubah.</Text>}

        {showPasswordForm && (
          <View style={{ gap: spacing.sm, marginTop: spacing.xs }}>
            <TextInput
              style={styles.fieldInput}
              placeholder="Password saat ini"
              placeholderTextColor={colors.inkFaint}
              secureTextEntry
              value={currentPassword}
              onChangeText={setCurrentPassword}
            />
            <TextInput
              style={styles.fieldInput}
              placeholder="Password baru (minimal 8 karakter)"
              placeholderTextColor={colors.inkFaint}
              secureTextEntry
              value={newPassword}
              onChangeText={setNewPassword}
            />
            <TextInput
              style={styles.fieldInput}
              placeholder="Konfirmasi password baru"
              placeholderTextColor={colors.inkFaint}
              secureTextEntry
              value={confirmPassword}
              onChangeText={setConfirmPassword}
            />
            {!!passwordError && <Text style={styles.errorText}>{passwordError}</Text>}
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <Pressable
                style={[styles.smallButton, styles.smallButtonPrimary]}
                disabled={savingPassword || !currentPassword || !newPassword}
                onPress={handleChangePassword}
              >
                {savingPassword ? (
                  <ActivityIndicator size="small" color={colors.ink} />
                ) : (
                  <Text style={styles.smallButtonLabel}>Simpan Password</Text>
                )}
              </Pressable>
              <Pressable
                style={styles.smallButton}
                disabled={savingPassword}
                onPress={() => {
                  setShowPasswordForm(false);
                  setPasswordError("");
                  setCurrentPassword("");
                  setNewPassword("");
                  setConfirmPassword("");
                }}
              >
                <Text style={styles.smallButtonLabel}>Batal</Text>
              </Pressable>
            </View>
          </View>
        )}
      </View>

      <View style={styles.divider} />

      <View style={[styles.profileField, styles.fieldRow]}>
        <View style={{ flex: 1 }}>
          <Text style={styles.fieldLabel}>NOTIFIKASI EMAIL</Text>
          <Text style={styles.fieldHint}>Kirim email tiap transkrip & ringkasan rapat selesai diproses.</Text>
        </View>
        <Switch
          value={user?.email_notifications ?? true}
          onValueChange={handleToggleNotif}
          disabled={savingNotif}
          trackColor={{ false: colors.border, true: colors.gold }}
          thumbColor={colors.white}
        />
      </View>

      <View style={styles.divider} />

      <View style={styles.dangerRow}>
        <Pressable style={styles.smallButton} onPress={handleLogout}>
          <Feather name="log-out" size={13} color={colors.ink} />
          <Text style={styles.smallButtonLabel}>Keluar</Text>
        </Pressable>
        <Pressable style={styles.dangerLink} onPress={() => setConfirmDeactivateOpen(true)}>
          <Feather name="trash-2" size={13} color={colors.danger} />
          <Text style={styles.dangerLinkLabel}>Nonaktifkan Akun</Text>
        </Pressable>
      </View>

      <Modal
        visible={confirmDeactivateOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setConfirmDeactivateOpen(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <View style={styles.modalIconWrap}>
              <Feather name="alert-triangle" size={20} color={colors.danger} />
            </View>
            <Text style={styles.modalTitle}>Nonaktifkan akun?</Text>
            <Text style={styles.modalBody}>
              Anda akan langsung keluar dan tidak bisa login lagi. Rapat yang sudah Anda rekam tetap tersimpan; hubungi
              admin kalau suatu saat ingin mengaktifkan kembali.
            </Text>
            {!!deactivateError && <Text style={styles.errorText}>{deactivateError}</Text>}
            <View style={styles.modalActions}>
              <Pressable style={styles.modalCancelButton} onPress={() => setConfirmDeactivateOpen(false)} disabled={deactivating}>
                <Text style={styles.modalCancelLabel}>Batal</Text>
              </Pressable>
              <Pressable style={styles.modalConfirmButton} onPress={handleDeactivate} disabled={deactivating}>
                {deactivating ? (
                  <ActivityIndicator size="small" color={colors.white} />
                ) : (
                  <Text style={styles.modalConfirmLabel}>Ya, Nonaktifkan</Text>
                )}
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

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

  // Back from Xendit without paying (?checkout=cancel), or a pending checkout
  // left over from earlier: drop it right away instead of "waiting" forever.
  async function dropPendingCheckout() {
    try {
      setSubscription(await cancelPendingCheckout());
    } catch (e) {
      setActionError(e.message || "Gagal membatalkan checkout");
    }
  }

  useEffect(() => {
    if (checkout === "cancel") dropPendingCheckout();
    else loadStatus();
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
  const inherited = !!subscription?.inherited_from_team;
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
        <Text style={styles.description}>Profil, paket langganan, dan preferensi akun.</Text>

        <Text style={styles.sectionTitle}>Profil Saya</Text>
        <ProfileCard />

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
            {subscription.status === "pending" && (
              <Pressable onPress={dropPendingCheckout}>
                <Text style={{ ...type.small, color: colors.goldDeep, fontWeight: "700" }}>Batalkan</Text>
              </Pressable>
            )}
          </View>
        )}
        {inherited && (
          <View style={styles.noticeBox}>
            <Feather name="users" size={14} color={colors.inkFaint} />
            <Text style={styles.noticeText}>
              Anda memakai paket <Text style={{ fontWeight: "700" }}>Team</Text> lewat team Anda. Paket ini berlaku selama
              langganan Team milik pemilik team masih aktif dan Anda masih menjadi anggota.
            </Text>
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
                <View style={styles.planIconWrap}>
                  <Feather name={plan.icon} size={18} color={colors.goldDeep} />
                </View>
                <View style={styles.planHeading}>
                  <Text style={styles.planName}>{plan.name}</Text>
                  <Text style={styles.planTagline}>{plan.tagline}</Text>
                </View>

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
                    disabled={isCurrent || scheduledCancel || inherited || pendingPlan === "cancel"}
                    onPress={() => setConfirmDowngradeOpen(true)}
                  >
                    {pendingPlan === "cancel" ? (
                      <ActivityIndicator size="small" color={colors.inkFaint} />
                    ) : (
                      <Text style={[styles.planButtonLabel, (isCurrent || scheduledCancel) && styles.planButtonLabelCurrent]}>
                        {isCurrent ? "Paket Saat Ini" : scheduledCancel ? "Dijadwalkan Turun" : inherited ? "Tidak berlaku" : "Turunkan ke Free"}
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
  scrollContent: { alignItems: "center", paddingVertical: spacing.lg, paddingHorizontal: "5%" },
  content: { gap: spacing.sm, width: "100%" },
  eyebrow: { ...type.eyebrow, color: colors.inkFaint },
  title: { ...type.h1, fontSize: 24, color: colors.ink, marginTop: 4 },
  description: { ...type.body, color: colors.inkSoft, marginTop: 2, marginBottom: spacing.md },
  sectionTitle: { ...type.h2, color: colors.ink, marginBottom: spacing.sm, marginTop: spacing.sm },
  errorText: { ...type.small, color: colors.danger, marginTop: 4 },
  savedText: { ...type.small, color: colors.success, marginTop: 4 },
  link: { ...type.small, fontWeight: "600", color: colors.info },

  profileCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
    gap: spacing.md,
    marginBottom: spacing.md,
    ...shadow.card,
  },
  profileHeader: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.ink,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarLabel: { color: colors.white, fontWeight: "700", fontSize: 16 },
  profileName: { ...type.bodyMedium, fontWeight: "700", fontSize: 16, color: colors.ink },
  profileEmail: { ...type.small, color: colors.inkFaint, marginTop: 1 },
  roleBadge: { backgroundColor: colors.goldSoft, borderRadius: radius.pill, paddingVertical: 3, paddingHorizontal: 10 },
  roleBadgeLabel: { ...type.small, fontWeight: "700", color: colors.goldDeep },

  divider: { height: 1, backgroundColor: colors.border },
  profileField: { gap: 6 },
  fieldLabel: { ...type.eyebrow, color: colors.inkFaint },
  fieldRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  fieldInput: {
    flex: 1,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceSunken,
    paddingHorizontal: spacing.md,
    paddingVertical: 9,
    ...type.body,
    color: colors.ink,
    outlineStyle: "none",
  },
  smallButton: {
    flexDirection: "row",
    gap: 6,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: 9,
    paddingHorizontal: spacing.md,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
  },
  smallButtonPrimary: { backgroundColor: colors.gold, borderColor: colors.gold },
  fieldHint: { ...type.small, color: colors.inkFaint, marginTop: 2 },
  dangerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  dangerLink: { flexDirection: "row", alignItems: "center", gap: 6 },
  dangerLinkLabel: { ...type.small, fontWeight: "600", color: colors.danger },
  smallButtonDisabled: { opacity: 0.5 },
  smallButtonLabel: { ...type.small, fontWeight: "700", color: colors.ink },

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
    ...shadow.card,
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

  planIconWrap: {
    width: 36,
    height: 36,
    borderRadius: radius.sm,
    backgroundColor: colors.goldSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  planHeading: { gap: 2 },
  planName: { ...type.h1, fontSize: 20, color: colors.ink },
  planTagline: { ...type.small, color: colors.inkFaint },

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
    ...shadow.card,
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
