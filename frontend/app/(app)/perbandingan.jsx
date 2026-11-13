import { Feather } from "@expo/vector-icons";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import { AnalysisCard } from "@/components/perbandingan/AnalysisCard";
import { CompareRow, SECTIONS } from "@/components/perbandingan/CompareRow";
import { HeadColumn } from "@/components/perbandingan/HeadColumn";
import { styles } from "@/components/perbandingan/styles";
import { colors } from "@/constants/theme";
import { getComparisonExportUrl, getMeeting, listMeetings } from "@/lib/api";
import { formatMeetingDate } from "@/lib/format";

// Hanya rapat dengan ringkasan sungguhan yang layak dibandingkan.
function comparable(meetings) {
  return meetings.filter((m) => m.status === "completed" && m.recording);
}

// Memuat detail satu rapat; halaman menyimpan keduanya supaya kedua sisi bisa ditata
// baris demi baris (tiap bagian A sejajar dengan bagian yang sama di B).
function useMeeting(meetingId) {
  const [state, setState] = useState({ status: "idle", data: null });

  useEffect(() => {
    if (!meetingId) {
      setState({ status: "idle", data: null });
      return;
    }
    let cancelled = false;
    setState({ status: "loading", data: null });
    getMeeting(meetingId)
      .then((data) => !cancelled && setState({ status: "done", data }))
      .catch(() => !cancelled && setState({ status: "error", data: null }));
    return () => {
      cancelled = true;
    };
  }, [meetingId]);

  return state;
}

export default function PerbandinganScreen() {
  const [status, setStatus] = useState("loading");
  const [meetings, setMeetings] = useState([]);
  const [leftId, setLeftId] = useState(null);
  const [rightId, setRightId] = useState(null);
  const left = useMeeting(leftId);
  const right = useMeeting(rightId);

  useEffect(() => {
    listMeetings()
      .then((data) => {
        const rows = comparable(data.map((m) => ({ ...m, ...formatMeetingDate(m.created_at) })));
        setMeetings(rows);
        setLeftId(rows[0]?.id ?? null);
        setRightId(rows[1]?.id ?? null);
        setStatus("done");
      })
      .catch(() => setStatus("error"));
  }, []);

  const notEnough = status === "done" && meetings.length < 2;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <View style={styles.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.title}>Perbandingan Rapat</Text>
            <Text style={styles.description}>Bandingkan ringkasan, keputusan, dan insight dua rapat secara berdampingan.</Text>
          </View>
          {leftId && rightId && (
            <Pressable style={styles.primaryButton} onPress={() => window.open(getComparisonExportUrl(leftId, rightId), "_blank")}>
              <Feather name="download" size={14} color={colors.ink} />
              <Text style={styles.primaryButtonLabel}>Export PDF</Text>
            </Pressable>
          )}
        </View>

        {status === "loading" && (
          <View style={styles.stateBox}>
            <ActivityIndicator color={colors.gold} />
          </View>
        )}
        {status === "error" && <Text style={styles.stateText}>Gagal memuat daftar rapat.</Text>}
        {notEnough && <Text style={styles.stateText}>Butuh minimal 2 rapat yang sudah selesai untuk dibandingkan.</Text>}

        {status === "done" && leftId && rightId && <AnalysisCard leftId={leftId} rightId={rightId} />}

        {status === "done" && meetings.length >= 2 && (
          <>
            <View style={styles.grid}>
              <HeadColumn state={left} allMeetings={meetings} meetingId={leftId} excludeId={rightId} onPick={setLeftId} label="RAPAT A" />
              <HeadColumn state={right} allMeetings={meetings} meetingId={rightId} excludeId={leftId} onPick={setRightId} label="RAPAT B" />
            </View>
            {SECTIONS.map((section) => (
              <CompareRow key={section.title} section={section} left={left} right={right} />
            ))}
          </>
        )}
      </View>
    </ScrollView>
  );
}
