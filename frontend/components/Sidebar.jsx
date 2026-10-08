import { Feather } from "@expo/vector-icons";
import { Link, router, usePathname } from "expo-router";
import { useEffect, useState } from "react";
import { Image, Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";
import { getBillingStatus, logout as apiLogout } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { initialsOf } from "@/lib/format";

const NAV_GROUPS = [
  {
    label: "Utama",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: "home" },
      { href: "/rapat", label: "Rapat", icon: "mic" },
    ],
  },
  {
    label: "Analisis",
    items: [
      { href: "/knowledge-base", label: "Knowledge Base", icon: "search" },
      { href: "/perbandingan", label: "Perbandingan", icon: "shuffle" },
      { href: "/laporan", label: "Laporan", icon: "bar-chart-2" },
    ],
  },
  { label: "Kolaborasi", items: [{ href: "/team", label: "Team", icon: "users" }] },
];
const ADMIN_GROUP = { label: "Administrasi", items: [{ href: "/admin", label: "Admin", icon: "shield" }] };

// A page counts as its menu item's page too when it is nested under it
// (/rapat/baru, /rapat/<id>, /team/gabung/<token> ...).
const isActive = (pathname, href) => pathname === href || pathname.startsWith(href + "/");

const PLAN_LABEL = { free: "Free", pro: "Pro", team: "Team" };

// Plan + this week's recording quota (Free only; Pro/Team have no cap).
// Re-read on every page change so it updates after a recording or an upgrade.
function PlanCard({ pathname }) {
  const [sub, setSub] = useState(null);
  useEffect(() => {
    const load = () => getBillingStatus().then(setSub).catch(() => {});
    load();
    // also after a plan-changing action (api.js) and when the tab regains focus
    window.addEventListener("notulis:plan-changed", load);
    window.addEventListener("focus", load);
    return () => {
      window.removeEventListener("notulis:plan-changed", load);
      window.removeEventListener("focus", load);
    };
  }, [pathname]);
  if (!sub) return null;

  const quota = sub.weekly_quota;
  const exhausted = quota && quota.remaining < 0.5;
  return (
    <View style={styles.planCard}>
      <Text style={styles.planEyebrow}>Plan Anda</Text>
      <Text style={styles.planName}>{(PLAN_LABEL[sub.plan] || sub.plan).toUpperCase()}</Text>
      {quota ? (
        <>
          <View style={styles.planRow}>
            <Text style={styles.planMeta}>Rekaman/minggu</Text>
            <Text style={[styles.planMeta, exhausted && { color: colors.danger, fontWeight: "700" }]}>
              {Math.round(quota.used)}/{quota.limit} mnt
            </Text>
          </View>
          <View style={styles.planTrack}>
            <View
              style={{
                width: `${Math.min(100, (quota.used / quota.limit) * 100)}%`,
                height: 5,
                backgroundColor: exhausted ? colors.danger : colors.gold,
              }}
            />
          </View>
        </>
      ) : (
        <Text style={styles.planMeta}>Rekaman tanpa batas</Text>
      )}
      <Link href="/pengaturan" asChild>
        <Pressable>
          <Text style={styles.planLink}>Lihat paket</Text>
        </Pressable>
      </Link>
    </View>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();
  // Only super_admin sees this — the backend independently enforces it too
  // (403 on /admin/stats for anyone else), this just keeps the link itself
  // from showing to someone who'd hit a wall clicking it.
  const groups = user?.role === "super_admin" ? [...NAV_GROUPS, ADMIN_GROUP] : NAV_GROUPS;

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
        <View style={styles.brand} accessibilityLabel="Notulis" accessible>
          <Image source={require("@/assets/images/logo.png")} style={styles.logo} resizeMode="contain" />
          <Text style={styles.brandLabel}>otulis</Text>
        </View>

        {groups.map((group) => (
          <View key={group.label} style={styles.group}>
            <Text style={styles.sectionLabel}>{group.label}</Text>
            <View style={styles.navList}>
              {group.items.map((item) => {
                const active = isActive(pathname, item.href);
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
        ))}
      </View>

      <View style={styles.footer}>
        <PlanCard pathname={pathname} />
        <Link href="/pengaturan" asChild>
          <Pressable style={StyleSheet.flatten([styles.navItem, isActive(pathname, "/pengaturan") && styles.navItemActive])}>
            <Feather name="settings" size={17} color={isActive(pathname, "/pengaturan") ? colors.ink : colors.inkSoft} />
            <Text
              style={StyleSheet.flatten([styles.navLabel, isActive(pathname, "/pengaturan") && styles.navLabelActive])}
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
            <Text style={styles.userRole}>{user?.role === "super_admin" ? "Super Admin" : "User"}</Text>
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
    width: 208,
    backgroundColor: colors.surface,
    borderRightWidth: 1,
    borderRightColor: colors.border,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.md,
    justifyContent: "space-between",
  },
  brand: { flexDirection: "row", alignItems: "center", gap: 2, marginBottom: spacing.xl, paddingHorizontal: spacing.xs },
  logo: { width: 26, height: 26 },
  brandLabel: { ...type.h1, color: colors.ink },
  sectionLabel: {
    ...type.eyebrow,
    color: colors.inkFaint,
    textTransform: "uppercase",
    marginBottom: spacing.sm,
    paddingHorizontal: spacing.xs,
  },
  group: { marginBottom: spacing.md },
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
  planCard: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: 6,
  },
  planEyebrow: { ...type.small, color: colors.inkFaint },
  planName: { ...type.h2, color: colors.ink },
  planRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  planMeta: { ...type.small, fontSize: 11.5, color: colors.inkSoft },
  planTrack: { height: 5, borderRadius: 3, backgroundColor: colors.border, overflow: "hidden" },
  planLink: { ...type.small, color: colors.goldDeep, fontWeight: "700", marginTop: 2 },
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
