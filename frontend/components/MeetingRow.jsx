import { Feather } from "@expo/vector-icons";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, spacing, type } from "@/constants/theme";
import { StatusPill } from "./StatusPill";

const PLATFORM_LABEL = {
  google_meet: "Google Meet",
  zoom: "Zoom",
};

const STATUS_DOT = {
  completed: colors.success,
  processing: colors.info,
  failed: colors.danger,
};

export function MeetingRow({ meeting }) {
  return (
    <Pressable style={styles.row}>
      <View style={[styles.dot, { backgroundColor: STATUS_DOT[meeting.status] }]} />
      <View style={styles.main}>
        <Text style={styles.title}>{meeting.title}</Text>
        <View style={styles.metaRow}>
          <Feather name="video" size={12} color={colors.inkFaint} />
          <Text style={styles.meta}>{PLATFORM_LABEL[meeting.platform]}</Text>
          <Text style={styles.metaDot}>·</Text>
          <Text style={styles.meta}>{meeting.durationMinutes} mnt</Text>
          <Text style={styles.metaDot}>·</Text>
          <Text style={styles.meta}>{meeting.participants} peserta</Text>
        </View>
      </View>
      <Text style={styles.time}>
        {meeting.date}, {meeting.time}
      </Text>
      <StatusPill status={meeting.status} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  dot: { width: 7, height: 7, borderRadius: 4 },
  main: { flex: 1, gap: 3 },
  title: { ...type.bodyMedium, color: colors.ink },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 5 },
  meta: { ...type.small, color: colors.inkFaint },
  metaDot: { color: colors.inkFaint, fontSize: 10 },
  time: { ...type.small, color: colors.inkFaint, width: 110 },
});
