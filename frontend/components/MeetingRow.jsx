import { Feather } from "@expo/vector-icons";
import { Link } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";
import { PLATFORM_LABEL } from "@/lib/format";
import { StatusPill } from "./StatusPill";

// Platform icon + accent color for the leading avatar circle — loosely
// evokes each brand's own color without needing brand icon assets (Feather
// has no Zoom/Meet marks, just a generic "video").
const PLATFORM_ACCENT = {
  google_meet: { icon: "video", bg: colors.successSoft, fg: colors.success },
  zoom: { icon: "video", bg: colors.infoSoft, fg: colors.info },
  upload: { icon: "upload", bg: colors.goldSoft, fg: colors.goldDeep },
};
const DEFAULT_ACCENT = { icon: "video", bg: colors.surfaceSunken, fg: colors.inkFaint };

export function MeetingRow({ meeting, selected, onSelect }) {
  const accent = PLATFORM_ACCENT[meeting.platform] || DEFAULT_ACCENT;

  // With onSelect the row just selects (Rapat page's preview pane); without it,
  // it navigates to the detail page as before (dashboard).
  const row = (
      <Pressable style={StyleSheet.flatten([styles.row, selected && styles.rowSelected])} onPress={onSelect}>
        <View style={[styles.iconCircle, { backgroundColor: accent.bg }]}>
          <Feather name={accent.icon} size={16} color={accent.fg} />
        </View>

        <View style={styles.main}>
          <Text style={styles.title} numberOfLines={1}>
            {meeting.title}
          </Text>
          <View style={styles.metaRow}>
            <Text style={styles.metaTag}>{PLATFORM_LABEL[meeting.platform] || meeting.platform}</Text>
            {meeting.isFromTeammate && (
              <View style={styles.metaItem}>
                <Feather name="users" size={11} color={colors.goldDeep} />
                <Text style={[styles.meta, { color: colors.goldDeep, fontWeight: "600" }]}>Dibagikan Team</Text>
              </View>
            )}
            {meeting.duration_minutes != null && (
              <View style={styles.metaItem}>
                <Feather name="clock" size={11} color={colors.inkFaint} />
                <Text style={styles.meta}>{meeting.duration_minutes} mnt</Text>
              </View>
            )}
            {meeting.estimated_participants != null && (
              <View style={styles.metaItem}>
                <Feather name="users" size={11} color={colors.inkFaint} />
                <Text style={styles.meta}>~{meeting.estimated_participants} peserta</Text>
              </View>
            )}
          </View>
        </View>

        <View style={styles.rightCol}>
          <Text style={styles.time}>
            {meeting.date}, {meeting.time}
          </Text>
          <StatusPill status={meeting.status} />
        </View>

        <Feather name="chevron-right" size={16} color={colors.inkFaint} />
      </Pressable>
  );
  return onSelect ? (
    row
  ) : (
    <Link href={`/rapat/${meeting.id}`} asChild>
      {row}
    </Link>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: 10,
    paddingHorizontal: spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  rowSelected: { backgroundColor: colors.goldSoft },
  iconCircle: {
    width: 34,
    height: 34,
    borderRadius: radius.pill,
    alignItems: "center",
    justifyContent: "center",
  },

  main: { flex: 1, gap: 2 },
  title: { ...type.bodyMedium, fontWeight: "600", color: colors.ink },
  metaRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 10 },
  metaTag: {
    ...type.small,
    fontWeight: "600",
    color: colors.inkSoft,
    backgroundColor: colors.surfaceSunken,
    borderRadius: radius.sm,
    paddingVertical: 2,
    paddingHorizontal: 7,
  },
  metaItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  meta: { ...type.small, color: colors.inkFaint },

  rightCol: { alignItems: "flex-end", gap: 6 },
  time: { ...type.small, color: colors.inkFaint },
});
