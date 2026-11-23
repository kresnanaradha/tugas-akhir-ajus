import { Feather } from "@expo/vector-icons";
import { router, usePathname } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { listMeetings } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatMeetingDate, initialsOf, PLATFORM_LABEL } from "@/lib/format";
import { StatusPill } from "./StatusPill";

const DAY_MS = 86400000;

export function TopBar() {
  const { user } = useAuth();
  const [search, setSearch] = useState("");
  const [recent, setRecent] = useState(null); // null = belum dimuat
  const [openMenu, setOpenMenu] = useState(null); // null | "bell"
  const pathname = usePathname();

  // menu ditutup juga kalau halaman berpindah lewat jalan lain (tombol kembali, tautan di halaman)
  useEffect(() => setOpenMenu(null), [pathname]);

  // pindah halaman dari dropdown: tutup menu lalu navigasi
  const go = (href) => {
    setOpenMenu(null);
    router.push(href);
  };

  // satu pengambilan data untuk badge (ada rapat 24 jam terakhir?) dan dropdown lonceng. Bilah ini ada di setiap halaman, jadi berjalan sekali per navigasi
  // super admin hanya mengelola sistem: tanpa pencarian rapat dan lonceng rapat (dan tanpa pengambilan datanya)
  const isAdmin = user?.role === "super_admin";
  useEffect(() => {
    if (isAdmin) return;
    listMeetings()
      .then((all) => setRecent(all.slice(0, 5).map((m) => ({ ...m, ...formatMeetingDate(m.created_at) }))))
      .catch(() => setRecent([]));
  }, [isAdmin]);

  const hasRecentActivity = recent?.some((m) => Date.now() - new Date(m.created_at).getTime() < DAY_MS);

  function runSearch() {
    const q = search.trim();
    if (!q) return;
    // cari di daftar Rapat (berdasarkan judul), bukan Knowledge Base: itu opt in dan hanya Pro
    router.push(`/rapat?q=${encodeURIComponent(q)}`);
    setSearch("");
  }

  return (
    <View style={styles.bar}>
      {isAdmin ? (
        <View />
      ) : (
        <View style={styles.search}>
          <Feather name="search" size={15} color={colors.inkFaint} />
          <TextInput
            placeholder="Cari rapat, transkrip..."
            placeholderTextColor={colors.inkFaint}
            style={styles.searchInput}
            value={search}
            onChangeText={setSearch}
            onSubmitEditing={runSearch}
            returnKeyType="search"
          />
        </View>
      )}

      <View style={styles.right}>
        {openMenu && <Pressable style={styles.overlay} onPress={() => setOpenMenu(null)} />}

        {!isAdmin && (
        <View style={openMenu === "bell" ? styles.raised : null}>
          <Pressable style={({ hovered }) => [styles.bellWrap, hovered && styles.hover]} onPress={() => setOpenMenu((m) => (m === "bell" ? null : "bell"))}>
            <Feather name="bell" size={18} color={colors.inkSoft} />
            {hasRecentActivity && <View style={styles.badge} />}
          </Pressable>
          {openMenu === "bell" && (
            <View style={[styles.dropdown, styles.bellDropdown]}>
              <Text style={styles.dropdownTitle}>Rapat Terbaru</Text>
              {recent?.length === 0 && <Text style={styles.dropdownEmpty}>Belum ada rapat.</Text>}
              {recent?.map((m) => (
                <Pressable key={m.id} style={({ hovered }) => [styles.recentRow, hovered && styles.hover]} onPress={() => go(`/rapat/${m.id}`)}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.recentTitle} numberOfLines={1}>
                      {m.title}
                    </Text>
                    <Text style={styles.recentMeta}>
                      {PLATFORM_LABEL[m.platform] || m.platform} · {m.date}, {m.time}
                    </Text>
                  </View>
                  <StatusPill status={m.status} />
                </Pressable>
              ))}
              <Pressable style={({ hovered }) => [styles.dropdownFooter, hovered && styles.hover]} onPress={() => go("/rapat")}>
                <Text style={styles.dropdownFooterLabel}>Lihat semua rapat</Text>
              </Pressable>
            </View>
          )}
        </View>
        )}

        {/* dropdown pengguna dibuang: Pengaturan, Billing, dan Keluar ada di sidebar */}
        <View style={styles.userChip}>
          <View style={styles.avatar}>
            <Text style={styles.avatarLabel}>{initialsOf(user?.name)}</Text>
          </View>
          <View>
            <Text style={styles.userName}>{user?.name}</Text>
            <Text style={styles.userRole}>{user?.role === "super_admin" ? "Super Admin" : "User"}</Text>
          </View>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    height: 56,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.surface,
    // membuat stacking context untuk bilah supaya dropdown (zIndex 50) tampil di atas isi halaman mana pun
    position: "relative",
    zIndex: 30,
  },
  search: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: colors.surfaceSunken,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    height: 38,
    width: 320,
  },
  searchInput: { ...type.body, color: colors.ink, flex: 1, outlineStyle: "none" },
  right: { flexDirection: "row", alignItems: "center", gap: spacing.lg },

  // menutupi layar di belakang dropdown yang terbuka supaya klik di mana saja menutupnya (tanpa dependensi tambahan)
  overlay: { position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 40 },

  hover: { backgroundColor: colors.surfaceSunken },
  // react-native-web memberi tiap View konteks tumpukan sendiri (z-index 0), jadi zIndex dropdown saja tidak cukup mengalahkan lapisan penutup
  raised: { zIndex: 50 },
  bellWrap: { position: "relative", padding: 6, borderRadius: radius.sm },
  badge: {
    position: "absolute",
    top: 2,
    right: 2,
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: colors.danger,
    borderWidth: 1.5,
    borderColor: colors.surface,
  },
  userChip: { flexDirection: "row", alignItems: "center", gap: 8 },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.ink,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarLabel: { color: colors.white, fontWeight: "700", fontSize: 12 },
  userName: { ...type.small, fontWeight: "600", color: colors.ink },
  userRole: { ...type.small, color: colors.inkFaint },

  dropdown: {
    position: "absolute",
    top: "100%",
    right: 0,
    marginTop: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    zIndex: 50,
    ...shadow.card,
  },
  bellDropdown: { width: 300, padding: spacing.sm },

  dropdownTitle: { ...type.eyebrow, color: colors.inkFaint, padding: spacing.sm, paddingBottom: 4 },
  dropdownEmpty: { ...type.small, color: colors.inkFaint, padding: spacing.sm },
  recentRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: 8,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.sm,
  },
  recentTitle: { ...type.small, fontWeight: "600", color: colors.ink },
  recentMeta: { ...type.small, color: colors.inkFaint, marginTop: 1 },
  dropdownFooter: { padding: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border, marginTop: 4 },
  dropdownFooterLabel: { ...type.small, fontWeight: "600", color: colors.info, textAlign: "center" },

});
