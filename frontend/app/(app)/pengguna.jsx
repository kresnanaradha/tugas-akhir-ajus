import { Redirect } from "expo-router";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, spacing, type } from "@/constants/theme";
import { useAuth } from "@/lib/auth-context";
import { UserManagement } from "@/components/UserManagement";

export default function PenggunaScreen() {
  const { user } = useAuth();

  // bukan super admin: dikembalikan daripada menampilkan halaman yang tidak bisa dipakai (backend menolak /admin/users juga)
  if (user && user.role !== "super_admin") {
    return <Redirect href="/dashboard" />;
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <View>
          <Text style={styles.eyebrow}>SUPER ADMIN</Text>
          <Text style={styles.title}>Manajemen Pengguna</Text>
          <Text style={styles.description}>Tambah pengguna, ubah peran, atur ulang password, dan aktifkan atau nonaktifkan akun.</Text>
        </View>
        <UserManagement currentUserId={user?.id} />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { alignItems: "center", paddingVertical: spacing.lg, paddingHorizontal: "5%" },
  content: { gap: spacing.md, width: "100%" },
  eyebrow: { ...type.eyebrow, color: colors.inkFaint },
  title: { ...type.h1, fontSize: 24, color: colors.ink, marginTop: 4 },
  description: { ...type.body, color: colors.inkSoft, marginTop: 2, maxWidth: 60 * 8 },
});
