import { Feather } from "@expo/vector-icons";
import { Link, router, usePathname } from "expo-router";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";
import { logout as apiLogout } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

function initialsOf(name) {
  return (name || "")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: "home" },
  { href: "/rapat", label: "Rapat", icon: "mic" },
  { href: "/knowledge-base", label: "Knowledge Base", icon: "search" },
  { href: "/perbandingan", label: "Perbandingan", icon: "shuffle" },
  { href: "/laporan", label: "Laporan", icon: "bar-chart-2" },
  { href: "/team", label: "Team", icon: "users" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();
  // Only super_admin sees this — the backend independently enforces it too
  // (403 on /admin/stats for anyone else), this just keeps the link itself
  // from showing to someone who'd hit a wall clicking it.
  const navItems = user?.role === "super_admin" ? [...NAV_ITEMS, { href: "/admin", label: "Admin", icon: "shield" }] : NAV_ITEMS;

  function handleLogout() {
    // Fire-and-forget on the server call — clear local auth state either
    // way so the UI can't get stuck showing a logged-in shell if the
    // request itself fails (e.g. backend already restarted, cookie's dead
    // anyway).
    apiLogout().catch(() => {});
    signOut();
    router.replace("/login");
  }

  return (
    <View style={styles.sidebar}>
      <View>
        <View style={styles.brand}>
          <Image source={require("@/assets/images/logo.png")} style={styles.logo} resizeMode="contain" />
          <Text style={styles.brandLabel}>Notulis</Text>
        </View>

        <Text style={styles.sectionLabel}>Menu</Text>
        <View style={styles.navList}>
          {navItems.map((item) => {
            const active = pathname === item.href;
            return (
              <Link key={item.href} href={item.href} asChild>
                <Pressable style={StyleSheet.flatten([styles.navItem, active && styles.navItemActive])}>
                  <Feather name={item.icon} size={17} color={active ? colors.ink : colors.inkSoft} />
                  <Text style={StyleSheet.flatten([styles.navLabel, active && styles.navLabelActive])}>{item.label}</Text>
                </Pressable>
              </Link>
            );
          })}
        </View>
      </View>

      <View style={styles.footer}>
        <Link href="/pengaturan" asChild>
          <Pressable style={StyleSheet.flatten([styles.navItem, pathname === "/pengaturan" && styles.navItemActive])}>
            <Feather name="settings" size={17} color={pathname === "/pengaturan" ? colors.ink : colors.inkSoft} />
            <Text
              style={StyleSheet.flatten([styles.navLabel, pathname === "/pengaturan" && styles.navLabelActive])}
            >
              Pengaturan
            </Text>
          </Pressable>
        </Link>
        <View style={styles.userRow}>
          <View style={styles.avatar}>
            <Text style={styles.avatarLabel}>{initialsOf(user?.name)}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.userName}>{user?.name}</Text>
            <Text style={styles.userRole}>{user?.role === "super_admin" ? "Super Admin" : "Admin"}</Text>
          </View>
          <Pressable onPress={handleLogout} hitSlop={8}>
            <Feather name="log-out" size={16} color={colors.inkFaint} />
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  sidebar: {
    width: 232,
    backgroundColor: colors.surface,
    borderRightWidth: 1,
    borderRightColor: colors.border,
    paddingVertical: spacing.xl,
    paddingHorizontal: spacing.lg,
    justifyContent: "space-between",
  },
  brand: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: spacing.xxl, paddingHorizontal: spacing.xs },
  logo: { width: 26, height: 26 },
  brandLabel: { ...type.h1, color: colors.ink },
  sectionLabel: {
    ...type.eyebrow,
    color: colors.inkFaint,
    textTransform: "uppercase",
    marginBottom: spacing.sm,
    paddingHorizontal: spacing.xs,
  },
  navList: { gap: 2 },
  navItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingVertical: 10,
    paddingHorizontal: spacing.md,
    borderRadius: radius.sm,
  },
  navItemActive: { backgroundColor: colors.gold },
  navLabel: { ...type.bodyMedium, color: colors.inkSoft },
  navLabelActive: { color: colors.ink, fontWeight: "700" },
  footer: { gap: spacing.md },
  userRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingTop: spacing.md,
    paddingHorizontal: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  avatar: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: colors.ink,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarLabel: { color: colors.white, fontWeight: "700", fontSize: 12.5 },
  userName: { ...type.small, fontWeight: "600", color: colors.ink },
  userRole: { ...type.small, color: colors.inkFaint },
});
