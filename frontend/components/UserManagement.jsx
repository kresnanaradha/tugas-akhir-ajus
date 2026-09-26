import { Feather } from "@expo/vector-icons";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { createUser, listUsers, resetUserPassword, updateUser } from "@/lib/api";

// Super admin's user management: list, add, change role, deactivate/activate
// (instead of deleting, since meetings point at the user's id) and reset a
// password. The backend enforces all of it (super_admin only, and no
// self-lockout); this just drives it.
export function UserManagement({ currentUserId }) {
  const [users, setUsers] = useState(null);
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "user" });
  const [resetFor, setResetFor] = useState(null); // user id whose reset form is open
  const [newPassword, setNewPassword] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    listUsers()
      .then(setUsers)
      .catch((e) => setError(e.message || "Gagal memuat pengguna"));
  }
  useEffect(load, []);

  // Runs one action, then reloads the list; any error is shown in one place.
  async function run(action, onDone) {
    setBusy(true);
    setError("");
    try {
      await action();
      onDone?.();
      load();
    } catch (e) {
      setError(e.message || "Gagal");
    } finally {
      setBusy(false);
    }
  }

  const change = (id, fields) => run(() => updateUser(id, fields));

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>Pengguna{users ? ` (${users.length})` : ""}</Text>
        <Pressable style={styles.smallButton} onPress={() => setAdding((v) => !v)}>
          <Feather name={adding ? "x" : "plus"} size={12} color={colors.ink} />
          <Text style={styles.smallButtonLabel}>{adding ? "Batal" : "Tambah Pengguna"}</Text>
        </Pressable>
      </View>

      {adding && (
        <View style={styles.form}>
          <View style={styles.formRow}>
            <TextInput
              style={[styles.input, { flex: 1 }]}
              placeholder="Nama"
              placeholderTextColor={colors.inkFaint}
              value={form.name}
              onChangeText={(name) => setForm((f) => ({ ...f, name }))}
            />
            <TextInput
              style={[styles.input, { flex: 1 }]}
              placeholder="Email"
              placeholderTextColor={colors.inkFaint}
              autoCapitalize="none"
              value={form.email}
              onChangeText={(email) => setForm((f) => ({ ...f, email }))}
            />
          </View>
          <View style={styles.formRow}>
            <TextInput
              style={[styles.input, { flex: 1 }]}
              placeholder="Password (minimal 8 karakter)"
              placeholderTextColor={colors.inkFaint}
              secureTextEntry
              value={form.password}
              onChangeText={(password) => setForm((f) => ({ ...f, password }))}
            />
            <Pressable
              style={styles.smallButton}
              onPress={() => setForm((f) => ({ ...f, role: f.role === "user" ? "super_admin" : "user" }))}
            >
              <Text style={styles.smallButtonLabel}>Peran: {form.role === "user" ? "User" : "Super Admin"}</Text>
            </Pressable>
            <Pressable
              style={[styles.smallButton, styles.primary]}
              disabled={busy}
              onPress={() =>
                run(
                  () => createUser(form),
                  () => {
                    setForm({ name: "", email: "", password: "", role: "user" });
                    setAdding(false);
                  }
                )
              }
            >
              <Text style={styles.smallButtonLabel}>Simpan</Text>
            </Pressable>
          </View>
        </View>
      )}

      {!!error && <Text style={styles.errorText}>{error}</Text>}
      {!users && !error && <ActivityIndicator color={colors.gold} />}

      {users?.map((u) => {
        const isSelf = u.id === currentUserId;
        return (
          <View key={u.id} style={[styles.row, !u.active && styles.rowInactive]}>
            <View style={styles.rowMain}>
              <View style={styles.nameLine}>
                <Text style={styles.name}>{u.name}</Text>
                {isSelf && <Text style={styles.selfTag}>Kamu</Text>}
                <View style={[styles.badge, u.role === "super_admin" && styles.badgeAdmin]}>
                  <Text style={styles.badgeLabel}>{u.role === "super_admin" ? "Super Admin" : "User"}</Text>
                </View>
                {!u.active && (
                  <View style={[styles.badge, styles.badgeOff]}>
                    <Text style={[styles.badgeLabel, { color: colors.danger }]}>Nonaktif</Text>
                  </View>
                )}
              </View>
              <Text style={styles.meta}>
                {u.email} · {u.meeting_count} rapat
              </Text>
            </View>

            {!isSelf && (
              <View style={styles.actions}>
                <Pressable
                  disabled={busy}
                  onPress={() => change(u.id, { role: u.role === "user" ? "super_admin" : "user" })}
                >
                  <Text style={styles.link}>{u.role === "user" ? "Jadikan Admin" : "Jadikan User"}</Text>
                </Pressable>
                <Pressable
                  disabled={busy}
                  onPress={() => {
                    setResetFor(resetFor === u.id ? null : u.id);
                    setNewPassword("");
                  }}
                >
                  <Text style={styles.link}>Reset Password</Text>
                </Pressable>
                <Pressable disabled={busy} onPress={() => change(u.id, { active: !u.active })}>
                  <Text style={[styles.link, u.active && { color: colors.danger }]}>
                    {u.active ? "Nonaktifkan" : "Aktifkan"}
                  </Text>
                </Pressable>
              </View>
            )}

            {resetFor === u.id && (
              <View style={styles.resetRow}>
                <TextInput
                  style={[styles.input, { flex: 1 }]}
                  placeholder="Password baru (minimal 8 karakter)"
                  placeholderTextColor={colors.inkFaint}
                  secureTextEntry
                  value={newPassword}
                  onChangeText={setNewPassword}
                />
                <Pressable
                  style={[styles.smallButton, styles.primary]}
                  disabled={busy}
                  onPress={() =>
                    run(
                      () => resetUserPassword(u.id, newPassword),
                      () => {
                        setResetFor(null);
                        setNewPassword("");
                      }
                    )
                  }
                >
                  <Text style={styles.smallButtonLabel}>Simpan</Text>
                </Pressable>
              </View>
            )}
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.sm,
    ...shadow.card,
  },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  title: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },
  form: {
    gap: spacing.sm,
    padding: spacing.sm,
    borderWidth: 1,
    borderColor: colors.gold,
    borderRadius: radius.sm,
    backgroundColor: colors.bg,
  },
  formRow: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  input: {
    ...type.small,
    color: colors.ink,
    paddingVertical: 7,
    paddingHorizontal: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    outlineStyle: "none",
  },
  smallButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingVertical: 6,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  primary: { backgroundColor: colors.gold, borderColor: colors.gold },
  smallButtonLabel: { ...type.small, fontWeight: "600", color: colors.ink },
  errorText: { ...type.small, color: colors.danger },

  row: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  rowInactive: { opacity: 0.6 },
  rowMain: { flex: 1, minWidth: 220, gap: 2 },
  nameLine: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" },
  name: { ...type.bodyMedium, fontWeight: "600", color: colors.ink },
  selfTag: { ...type.small, color: colors.inkFaint },
  meta: { ...type.small, color: colors.inkFaint },
  badge: { borderRadius: radius.pill, paddingVertical: 1, paddingHorizontal: 8, backgroundColor: colors.bg },
  badgeAdmin: { backgroundColor: colors.goldSoft },
  badgeOff: { backgroundColor: "#FBE9E7" },
  badgeLabel: { ...type.small, fontWeight: "700", color: colors.inkSoft },
  actions: { flexDirection: "row", gap: spacing.lg },
  link: { ...type.small, fontWeight: "600", color: colors.info },
  resetRow: { flexDirection: "row", gap: spacing.sm, alignItems: "center", width: "100%" },
});
