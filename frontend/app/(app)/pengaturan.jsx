import { Feather } from "@expo/vector-icons";
import { router } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { changePassword, deactivateAccount, logout as apiLogout, updateProfile } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { initialsOf } from "@/lib/format";

// satu kolom teks dengan tombol Simpan dan umpan balik sendiri, dipakai untuk Nama / Email / Nomor Telepon. Mengandaikan initialValue
// sudah dimuat (layout hanya merender setelah user ada). allowEmpty membuat kolom opsional seperti telepon bisa dikosongkan
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
      // Sebisanya - saklarnya tetap di nilai saat ini (belum tersimpan)
      // kalau ini gagal, tanpa banner error terpisah untuk satu saklar.
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
  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <Text style={styles.eyebrow}>MENU</Text>
        <Text style={styles.title}>Pengaturan</Text>
        <Text style={styles.description}>Profil dan preferensi akun. Paket langganan ada di menu Billing.</Text>

        <Text style={styles.sectionTitle}>Profil Saya</Text>
        <ProfileCard />
      </View>
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
