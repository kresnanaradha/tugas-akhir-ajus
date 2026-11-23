import { Redirect } from "expo-router";
import { useEffect, useState } from "react";
import { Feather } from "@expo/vector-icons";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { getAdminQueue, getAdminWorkers } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { PLATFORM_LABEL } from "@/lib/format";
import { StatCard } from "@/components/StatCard";

const REFRESH_MS = 5000; // sama dengan jarak detak transkriber (TTL detaknya 15 detik)

function StatusPill({ busy, busyLabel, idleLabel }) {
  const s = busy
    ? { label: busyLabel, fg: colors.danger, bg: colors.dangerSoft }
    : { label: idleLabel, fg: colors.success, bg: colors.successSoft };
  return <Text style={[styles.pill, { color: s.fg, backgroundColor: s.bg }]}>{s.label}</Text>;
}

export default function BotScreen() {
  const { user } = useAuth();
  const [workers, setWorkers] = useState(null); // null = belum dimuat
  const [queue, setQueue] = useState(null);

  useEffect(() => {
    if (user?.role !== "super_admin") return;
    let alive = true;
    const load = () => {
      // dua pemanggilan terpisah: yang satu gagal, yang lain tetap tampil
      getAdminWorkers().then((d) => alive && setWorkers(d)).catch(() => alive && setWorkers((w) => w ?? []));
      getAdminQueue().then((d) => alive && setQueue(d)).catch(() => {});
    };
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [user]);

  // bukan super admin: dikembalikan daripada menampilkan halaman yang tidak bisa dipakai (backend menolak /admin/workers juga)
  if (user && user.role !== "super_admin") {
    return <Redirect href="/dashboard" />;
  }

  const transcribers = queue?.transcribers ?? [];

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <View>
          <Text style={styles.eyebrow}>SUPER ADMIN</Text>
          <Text style={styles.title}>Bot Perekam</Text>
          <Text style={styles.description}>
            Keadaan bot perekam, antrean rapat, dan pemrosesan hasil rapat. Halaman ini diperbarui otomatis tiap beberapa detik.
          </Text>
        </View>

        <Text style={styles.sectionLabel}>Bot Perekam</Text>
        <View style={styles.card}>
          {workers === null ? (
            <ActivityIndicator color={colors.gold} />
          ) : workers.length === 0 ? (
            <Text style={styles.description}>Tidak ada bot perekam yang aktif. Rapat baru akan menunggu sampai ada bot yang menyala.</Text>
          ) : (
            workers.map((w, i) => (
              <View key={w.id} style={[styles.row, i > 0 && styles.rowDivider]}>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={styles.name}>
                    Perekam {i + 1} <Text style={styles.id}>({w.id})</Text>
                  </Text>
                  <Text style={styles.meta}>
                    Bisa merekam: {w.platforms.map((p) => PLATFORM_LABEL[p] || p).join(", ") || "tidak ada platform"}
                  </Text>
                  {w.google_expired && (
                    <Text style={[styles.meta, { color: colors.danger }]}>
                      Sesi Google habis, Google Meet dinonaktifkan. Login ulang akun bot lewat noVNC.
                    </Text>
                  )}
                </View>
                {w.vnc_port && (
                  // membuka noVNC di komputermu sendiri (localhost), jadi tidak ada port yang dibuka ke internet
                  <Pressable
                    style={[styles.vncButton, w.google_expired && styles.vncButtonAlert]}
                    onPress={() => window.open(`http://localhost:${w.vnc_port}/vnc.html`, "_blank")}
                  >
                    <Feather name="monitor" size={12} color={colors.ink} />
                    <Text style={styles.vncButtonLabel}>VNC</Text>
                  </Pressable>
                )}
                <StatusPill busy={w.busy} busyLabel="Sedang merekam" idleLabel="Siap merekam" />
              </View>
            ))
          )}
        </View>
        {workers?.some((w) => w.vnc_port) && (
          <Text style={styles.hint}>
            Tombol VNC membuka layar bot di komputermu lewat localhost. Di server, jalankan dulu terowongan SSH:
            ssh -L 6080:localhost:6080 -L 6081:localhost:6081 -L 6082:localhost:6082 (user)@(server). Password VNC ada di
            .env (VNC_PASSWORD).
          </Text>
        )}

        <Text style={styles.sectionLabel}>Antrean dan Pemrosesan Hasil</Text>
        <View style={styles.statRow}>
          <StatCard value={queue?.join?.google_meet ?? "-"} label="Menunggu perekam, Google Meet" />
          <StatCard value={queue?.join?.zoom ?? "-"} label="Menunggu perekam, Zoom" />
          <StatCard value={queue?.transcription ?? "-"} label="Menunggu transkripsi" />
          <StatCard
            value={queue?.dead ?? "-"}
            label="Job menyerah setelah 3 kali gagal"
            delta={queue?.dead > 0 ? "Perlu dicek di Redis" : null}
            deltaColor={colors.danger}
          />
        </View>

        <Text style={styles.sectionLabel}>Transkriber</Text>
        <View style={styles.card}>
          {queue === null ? (
            <ActivityIndicator color={colors.gold} />
          ) : transcribers.length === 0 ? (
            <Text style={styles.description}>Tidak ada transkriber yang aktif. Hasil rapat akan menunggu sampai ada yang menyala.</Text>
          ) : (
            transcribers.map((t, i) => (
              <View key={t.id} style={[styles.row, i > 0 && styles.rowDivider]}>
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={styles.name}>
                    Transkriber {i + 1} <Text style={styles.id}>({t.id})</Text>
                  </Text>
                  <Text style={styles.meta}>{t.busy ? `Mengerjakan rapat ${t.meeting_id}` : "Menunggu job"}</Text>
                </View>
                <StatusPill busy={t.busy} busyLabel="Sedang memproses" idleLabel="Siap" />
              </View>
            ))
          )}
        </View>
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
  sectionLabel: { ...type.eyebrow, color: colors.inkFaint, marginTop: spacing.md },
  statRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },

  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    ...shadow.card,
  },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm },
  rowDivider: { borderTopWidth: 1, borderTopColor: colors.border },
  name: { ...type.bodyMedium, fontWeight: "600", color: colors.ink },
  id: { ...type.small, fontWeight: "400", color: colors.inkFaint },
  meta: { ...type.small, color: colors.inkSoft },
  hint: { ...type.small, color: colors.inkFaint, maxWidth: 80 * 8 },
  vncButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: 4,
    paddingHorizontal: 10,
    backgroundColor: colors.surface,
  },
  vncButtonAlert: { backgroundColor: colors.gold, borderColor: colors.gold },
  vncButtonLabel: { ...type.small, fontWeight: "700", color: colors.ink },
  pill: { ...type.small, fontWeight: "600", borderRadius: radius.pill, paddingVertical: 3, paddingHorizontal: 10, overflow: "hidden" },
});
