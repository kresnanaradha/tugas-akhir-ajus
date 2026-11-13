import { Feather } from "@expo/vector-icons";
import { Pressable, ScrollView, Text, View } from "react-native";

import { colors, radius } from "@/constants/theme";
import { getRecordingUrl } from "@/lib/api";
import { formatBytes, formatElapsed } from "@/lib/transcript";

import { SpeakerBadge } from "./SpeakerBadge";
import { styles } from "./styles";

// tab Transkrip: video rekaman di kiri, transkrip per baris di kanan. Baris yang sedang diputar disorot, klik baris
// untuk melompat ke waktunya
export function TranskripTab({ meeting, videoRef, currentTime, setCurrentTime, seekTo }) {
  return (
    <View style={styles.section}>
      <View style={styles.mediaGrid}>
        <View style={styles.videoCol}>
          {/* <video> mentah (aplikasi web saja): kontrol bawaan browser menangani putar, geser, dan durasi */}
          <video
            ref={videoRef}
            controls
            style={{ width: "100%", borderRadius: radius.md, backgroundColor: "#000", aspectRatio: "16/9" }}
            src={getRecordingUrl(meeting.id)}
            onTimeUpdate={(e) => setCurrentTime(e.target.currentTime)}
          />
          <View style={styles.fileInfoRow}>
            <Text style={styles.fileInfoText}>
              {meeting.file_extension && `Format: ${meeting.file_extension.toUpperCase()}`}
              {meeting.file_extension && meeting.file_size_bytes != null && " · "}
              {formatBytes(meeting.file_size_bytes) && `Ukuran: ${formatBytes(meeting.file_size_bytes)}`}
            </Text>
            {/* <a download> mentah: unduhan file biasa */}
            <a href={getRecordingUrl(meeting.id)} download style={{ textDecorationLine: "none" }}>
              <View style={styles.downloadBtn}>
                <Feather name="download" size={13} color={colors.ink} />
                <Text style={styles.downloadLabel}>Unduh</Text>
              </View>
            </a>
          </View>
        </View>

        <View style={styles.transcriptCol}>
          {meeting.segments ? (
            <ScrollView style={styles.transcriptScroll}>
              {meeting.segments.map((seg, i) => {
                const active = seg.start != null && currentTime >= seg.start && currentTime < seg.end;
                return (
                  <Pressable
                    key={i}
                    style={[styles.segmentRow, active && styles.segmentRowActive]}
                    onPress={() => seekTo(seg.start)}
                  >
                    <View style={styles.segmentHeader}>
                      {seg.start != null && <Text style={styles.segmentTime}>{formatElapsed(Math.floor(seg.start))}</Text>}
                      <SpeakerBadge speaker={seg.speaker} />
                    </View>
                    <Text style={styles.segmentText}>{seg.text}</Text>
                  </Pressable>
                );
              })}
            </ScrollView>
          ) : meeting.fixed_transcript || meeting.transcript ? (
            <ScrollView style={styles.transcriptScroll}>
              {/* transkrip perbaikan AI kalau ada, kalau tidak yang mentah */}
              <Text style={styles.plainTranscript}>{meeting.fixed_transcript || meeting.transcript}</Text>
            </ScrollView>
          ) : (
            <Text style={styles.errorText}>{meeting.transcript_error ? `Transkrip gagal: ${meeting.transcript_error}.` : "Tidak ada percakapan yang terdeteksi dalam rekaman ini."}</Text>
          )}
        </View>
      </View>
      {!meeting.segments && !!meeting.transcript && (
        <Text style={styles.syncNote}>
          Rapat ini direkam sebelum fitur sinkronisasi waktu ada, jadi transkrip tampil apa adanya tanpa
          highlight per baris.
        </Text>
      )}
    </View>
  );
}
