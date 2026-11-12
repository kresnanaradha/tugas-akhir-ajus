import { Feather } from "@expo/vector-icons";
import { ActivityIndicator, Modal, Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";

// modal konfirmasi untuk aksi berbahaya (hapus, nonaktifkan, keluar team, turun paket). busy mengunci tombol dan
// menampilkan spinner selama aksinya berjalan
export function ConfirmModal({ visible, icon = "alert-triangle", title, body, error, confirmLabel, busy, onCancel, onConfirm }) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={() => !busy && onCancel()}>
      <View style={styles.overlay}>
        <View style={styles.card}>
          <View style={styles.iconWrap}>
            <Feather name={icon} size={20} color={colors.danger} />
          </View>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.body}>{body}</Text>
          {!!error && <Text style={styles.error}>{error}</Text>}
          <View style={styles.actions}>
            <Pressable style={styles.cancelButton} onPress={onCancel} disabled={busy}>
              <Text style={styles.cancelLabel}>Batal</Text>
            </Pressable>
            <Pressable style={styles.confirmButton} onPress={onConfirm} disabled={busy}>
              {busy ? <ActivityIndicator size="small" color={colors.white} /> : <Text style={styles.confirmLabel}>{confirmLabel}</Text>}
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: "rgba(27,31,43,0.45)", alignItems: "center", justifyContent: "center", padding: spacing.lg },
  card: { maxWidth: 360, width: "100%", backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.lg, alignItems: "center", gap: spacing.sm },
  iconWrap: { width: 44, height: 44, borderRadius: radius.sm, backgroundColor: colors.dangerSoft, alignItems: "center", justifyContent: "center", marginBottom: spacing.xs },
  title: { ...type.h2, color: colors.ink, textAlign: "center" },
  body: { ...type.body, color: colors.inkSoft, textAlign: "center", lineHeight: 19 },
  error: { ...type.small, color: colors.danger, textAlign: "center" },
  actions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, alignSelf: "stretch" },
  cancelButton: { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingVertical: 11, alignItems: "center" },
  cancelLabel: { ...type.bodyMedium, fontWeight: "600", color: colors.ink },
  confirmButton: { flex: 1, backgroundColor: colors.danger, borderRadius: radius.sm, paddingVertical: 11, alignItems: "center" },
  confirmLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.white },
});
