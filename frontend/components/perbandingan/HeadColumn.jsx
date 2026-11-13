// kolom kepala satu sisi perbandingan: pemilih rapat dan kartu header rapat terpilih (judul, tanggal, status)
import { Feather } from "@expo/vector-icons";
import { router } from "expo-router";
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { StatusPill } from "@/components/StatusPill";
import { styles } from "@/components/perbandingan/styles";
import { colors, radius } from "@/constants/theme";
import { formatMeetingDate, PLATFORM_LABEL } from "@/lib/format";

// Aksen per platform yang sama dengan components/MeetingRow.jsx, di sini sebagai tepi atas
// berwarna di kartu header tiap rapat.
const PLATFORM_ACCENT = {
  google_meet: colors.success,
  zoom: colors.info,
  upload: colors.gold,
};

// <select> mentah (aplikasi web saja): dropdown bawaan menangani daftar panjang dan keyboard. appearance none membuang
// panah bawaan browser supaya chevron Feather sesuai dengan sisa aplikasi
function MeetingPicker({ meetings, value, onChange, placeholder }) {
  return (
    <View style={{ position: "relative", justifyContent: "center" }}>
      <select
        value={value || ""}
        onChange={(e) => onChange(e.target.value || null)}
        style={{
          width: "100%",
          padding: "11px 36px 11px 12px",
          borderRadius: radius.sm,
          border: `1px solid ${colors.border}`,
          backgroundColor: colors.surface,
          color: colors.ink,
          fontSize: 14.5,
          outline: "none",
          appearance: "none",
          WebkitAppearance: "none",
          cursor: "pointer",
        }}
      >
        <option value="">{placeholder}</option>
        {meetings.map((m) => (
          <option key={m.id} value={m.id} disabled={m.id === value}>
            {m.title} · {m.date}, {m.time}
          </option>
        ))}
      </select>
      <Feather name="chevron-down" size={16} color={colors.inkFaint} style={{ position: "absolute", right: 12, pointerEvents: "none" }} />
    </View>
  );
}

export function HeadColumn({ state, meetingId, allMeetings, excludeId, onPick, label }) {
  const picker = (
    <>
      <Text style={styles.colLabel}>{label}</Text>
      <MeetingPicker
        meetings={allMeetings.filter((m) => m.id !== excludeId)}
        value={meetingId}
        onChange={onPick}
        placeholder="Pilih rapat..."
      />
    </>
  );

  if (state.status !== "done") {
    return (
      <View style={styles.col}>
        {picker}
        {state.status === "loading" && (
          <View style={styles.stateBox}>
            <ActivityIndicator color={colors.gold} />
          </View>
        )}
        {state.status === "error" && <Text style={styles.stateText}>Gagal memuat rapat ini.</Text>}
      </View>
    );
  }

  const meeting = state.data;
  const { date, time } = formatMeetingDate(meeting.created_at);

  return (
    <View style={styles.col}>
      {picker}
      <View style={[styles.headCard, { borderTopColor: PLATFORM_ACCENT[meeting.platform] || colors.border }]}>
        <View style={styles.headTop}>
          <StatusPill status={meeting.status} />
          <Text style={styles.platformLabel}>{PLATFORM_LABEL[meeting.platform] || meeting.platform}</Text>
        </View>
        <Text style={styles.meetingTitle} numberOfLines={2}>
          {meeting.title}
        </Text>
        <View style={styles.metaRow}>
          <View style={styles.metaItem}>
            <Feather name="calendar" size={12} color={colors.inkFaint} />
            <Text style={styles.metaText}>
              {date}, {time}
            </Text>
          </View>
          {meeting.duration_minutes != null && (
            <View style={styles.metaItem}>
              <Feather name="clock" size={12} color={colors.inkFaint} />
              <Text style={styles.metaText}>{meeting.duration_minutes} mnt</Text>
            </View>
          )}
          {meeting.estimated_participants != null && (
            <View style={styles.metaItem}>
              <Feather name="users" size={12} color={colors.inkFaint} />
              <Text style={styles.metaText}>~{meeting.estimated_participants} peserta</Text>
            </View>
          )}
        </View>
        <Pressable style={styles.detailButton} onPress={() => router.push(`/rapat/${meeting.id}`)}>
          <Text style={styles.detailButtonLabel}>Lihat Detail</Text>
          <Feather name="chevron-right" size={13} color={colors.inkSoft} />
        </Pressable>
      </View>
    </View>
  );
}
