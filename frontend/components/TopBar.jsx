import { Feather } from "@expo/vector-icons";
import { Link, router } from "expo-router";
import { useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { listMeetings, logout as apiLogout } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { formatMeetingDate, initialsOf, PLATFORM_LABEL } from "@/lib/format";
import { StatusPill } from "./StatusPill";

const DAY_MS = 86400000;

export function TopBar() {
  const { user, signOut } = useAuth();
  const [search, setSearch] = useState("");
  const [recent, setRecent] = useState(null); // null = not loaded yet
  const [openMenu, setOpenMenu] = useState(null); // null | "bell" | "user"

  // One fetch, shared by the badge (any meeting from the last 24h?) and the
  // bell dropdown's content — TopBar is mounted on every page, so this runs
  // once per navigation rather than only when the bell is actually opened.
  useEffect(() => {
    listMeetings()
      .then((all) => setRecent(all.slice(0, 5).map((m) => ({ ...m, ...formatMeetingDate(m.created_at) }))))
      .catch(() => setRecent([]));
  }, []);

  const hasRecentActivity = recent?.some((m) => Date.now() - new Date(m.created_at).getTime() < DAY_MS);

  function runSearch() {
    const q = search.trim();
    if (!q) return;
    // The Rapat list (filter by title), not Knowledge Base — KB is a
    // narrower, opt-in, Pro+-only search over a handful of meetings, not
    // what "cari rapat" should mean for everyone.
    router.push(`/rapat?q=${encodeURIComponent(q)}`);
    setSearch("");
  }

  function handleLogout() {
    apiLogout().catch(() => {});
    signOut();
    router.replace("/login");
  }

  return (
    <View style={styles.bar}>
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

      <View style={styles.right}>
        {openMenu && <Pressable style={styles.overlay} onPress={() => setOpenMenu(null)} />}

        <View>
          <Pressable style={styles.bellWrap} onPress={() => setOpenMenu((m) => (m === "bell" ? null : "bell"))}>
            <Feather name="bell" size={18} color={colors.inkSoft} />
            {hasRecentActivity && <View style={styles.badge} />}
          </Pressable>
          {openMenu === "bell" && (
            <View style={[styles.dropdown, styles.bellDropdown]}>
              <Text style={styles.dropdownTitle}>Rapat Terbaru</Text>
              {recent?.length === 0 && <Text style={styles.dropdownEmpty}>Belum ada rapat.</Text>}
              {recent?.map((m) => (
                <Link key={m.id} href={`/rapat/${m.id}`} asChild>
                  <Pressable style={styles.recentRow} onPress={() => setOpenMenu(null)}>
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
                </Link>
              ))}
              <Link href="/rapat" asChild>
                <Pressable style={styles.dropdownFooter} onPress={() => setOpenMenu(null)}>
                  <Text style={styles.dropdownFooterLabel}>Lihat semua rapat</Text>
                </Pressable>
              </Link>
            </View>
          )}
        </View>

        <View>
          <Pressable style={styles.userChip} onPress={() => setOpenMenu((m) => (m === "user" ? null : "user"))}>
            <View style={styles.avatar}>
              <Text style={styles.avatarLabel}>{initialsOf(user?.name)}</Text>
            </View>
            <View>
              <Text style={styles.userName}>{user?.name}</Text>
              <Text style={styles.userRole}>{user?.role === "super_admin" ? "Super Admin" : "User"}</Text>
            </View>
            <Feather name="chevron-down" size={14} color={colors.inkFaint} />
          </Pressable>
          {openMenu === "user" && (
            <View style={[styles.dropdown, styles.userDropdown]}>
              <Link href="/pengaturan" asChild>
                <Pressable style={styles.menuItem} onPress={() => setOpenMenu(null)}>
                  <Feather name="settings" size={14} color={colors.inkSoft} />
                  <Text style={styles.menuItemLabel}>Pengaturan</Text>
                </Pressable>
              </Link>
              <Pressable style={styles.menuItem} onPress={handleLogout}>
                <Feather name="log-out" size={14} color={colors.danger} />
                <Text style={[styles.menuItemLabel, { color: colors.danger }]}>Keluar</Text>
              </Pressable>
            </View>
          )}
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
    // Establishes a stacking context for the whole bar so the dropdowns
    // below (position: absolute, zIndex: 50 within this context) paint
    // above every page's own content — without this, a page's own buttons
    // (zIndex: auto) could still end up painted on top purely by DOM order,
    // since position:relative alone doesn't create a stacking context.
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

  // Covers the whole screen behind an open dropdown so a click anywhere
  // else closes it — simplest cross-platform "click outside" without a new
  // dependency. Sits under the dropdowns (lower zIndex) but above the page.
  overlay: { position: "fixed", top: 0, left: 0, right: 0, bottom: 0, zIndex: 40 },

  bellWrap: { position: "relative", padding: 4 },
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
  userDropdown: { width: 180, padding: 6 },

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

  menuItem: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 9, paddingHorizontal: spacing.sm, borderRadius: radius.sm },
  menuItemLabel: { ...type.small, fontWeight: "600", color: colors.ink },
});
