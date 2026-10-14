import { Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing, type } from "@/constants/theme";

// menampilkan hasil {transcript, fixed_transcript, summary, ..._error} dari sebuah upload. Tanpa scroll sendiri, halamannya yang scroll.
// onDone menambah tombol "Tutup", hilangkan kalau hanya menampilkan hasil
export function PipelineResult({ result, onDone }) {
  const summary = result.summary;

  return (
    <View>
      {summary && (
        <>
          {!!summary.short_summary && (
            <>
              <Text style={styles.sectionLabel}>RINGKASAN</Text>
              <Text style={styles.body}>{summary.short_summary}</Text>
            </>
          )}
          <Text style={styles.sectionLabel}>POKOK PEMBAHASAN RAPAT</Text>
          <Text style={styles.body}>{summary.executive_summary}</Text>

          {summary.key_decisions?.length > 0 && (
            <>
              <Text style={styles.sectionLabel}>KEPUTUSAN</Text>
              {summary.key_decisions.map((item, i) => (
                <Text key={i} style={styles.bullet}>
                  • {item}
                </Text>
              ))}
            </>
          )}

          {summary.topics_discussed?.length > 0 && (
            <>
              <Text style={styles.sectionLabel}>TOPIK DIBAHAS</Text>
              {summary.topics_discussed.map((item, i) => (
                <Text key={i} style={styles.bullet}>
                  • {item}
                </Text>
              ))}
            </>
          )}
        </>
      )}

      {!summary && (
        <Text style={styles.errorText}>
          Ringkasan gagal: {result.summary_error || "tidak diketahui"}. Transkrip tetap tersimpan.
        </Text>
      )}

      {result.transcript && (
        <>
          <Text style={styles.sectionLabel}>TRANSKRIP</Text>
          <Text style={styles.transcript}>{result.transcript}</Text>
        </>
      )}

      {onDone && (
        <Pressable style={styles.done} onPress={onDone}>
          <Text style={styles.doneLabel}>Tutup</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  sectionLabel: { ...type.eyebrow, color: colors.inkFaint, marginTop: spacing.md, marginBottom: 6 },
  body: { ...type.body, color: colors.ink },
  bullet: { ...type.body, color: colors.ink, marginBottom: 4 },
  transcript: { ...type.small, color: colors.inkSoft, lineHeight: 19 },
  errorText: { ...type.body, color: colors.danger },
  done: {
    backgroundColor: colors.surfaceSunken,
    borderRadius: radius.sm,
    paddingVertical: 12,
    alignItems: "center",
    marginTop: spacing.lg,
  },
  doneLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },
});
