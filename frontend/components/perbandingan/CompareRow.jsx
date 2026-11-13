// baris perbandingan: bagian yang sama dari rapat A dan B berdampingan
import { Feather } from "@expo/vector-icons";
import { router } from "expo-router";
import { Pressable, Text, View } from "react-native";
import { SectionCard } from "@/components/perbandingan/SectionCard";
import { styles } from "@/components/perbandingan/styles";
import { colors } from "@/constants/theme";

// Satu baris perbandingan per bagian, dalam urutan permintaan dosen: topik
// dulu, ringkasan (dipotong) sesudahnya. Masing-masing merender kartu SATU rapat.
export const SECTIONS = [
  {
    icon: "hash",
    title: "Topik Dibahas",
    count: (s) => (s.topics_discussed || []).length,
    body: (s) => {
      const topics = s.topics_discussed || [];
      return (
        <View style={styles.chipRow}>
          {topics.map((t, i) => (
            <View key={i} style={styles.chip}>
              <Text style={styles.chipLabel}>{t}</Text>
            </View>
          ))}
          {topics.length === 0 && <Text style={styles.mutedText}>Tidak ada topik tercatat.</Text>}
        </View>
      );
    },
  },
  {
    icon: "align-left",
    title: "Ringkasan",
    body: (s, meeting) => (
      <>
        <Text style={styles.bodyText} numberOfLines={5}>
          {s.short_summary || s.executive_summary}
        </Text>
        <Pressable onPress={() => router.push(`/rapat/${meeting.id}`)}>
          <Text style={styles.moreLink}>Baca selengkapnya</Text>
        </Pressable>
      </>
    ),
  },
  {
    icon: "check-circle",
    title: "Keputusan",
    count: (s) => (s.key_decisions || []).length,
    body: (s) => {
      const decisions = s.key_decisions || [];
      return (
        <>
          {decisions.map((d, i) => (
            <View key={i} style={styles.bulletRow}>
              <Feather name="check-circle" size={13} color={colors.success} style={{ marginTop: 3 }} />
              <Text style={[styles.bodyText, { flex: 1 }]}>{d}</Text>
            </View>
          ))}
          {decisions.length === 0 && <Text style={styles.mutedText}>Tidak ada keputusan tercatat.</Text>}
        </>
      );
    },
  },
  {
    icon: "list",
    title: "Action Items",
    count: (s) => (s.action_items || []).length,
    body: (s) => {
      const items = s.action_items || [];
      return (
        <>
          {items.map((a, i) => (
            <View key={i} style={styles.bulletRow}>
              <Feather
                name={a.done ? "check-square" : "square"}
                size={14}
                color={a.done ? colors.success : colors.inkFaint}
                style={{ marginTop: 2 }}
              />
              <Text style={[styles.bodyText, { flex: 1 }, a.done && styles.done]}>
                {a.task}
                {a.assignee || a.due ? (
                  <Text style={styles.mutedText}>{`  (${[a.assignee, a.due].filter(Boolean).join(" · ")})`}</Text>
                ) : null}
              </Text>
            </View>
          ))}
          {items.length === 0 && <Text style={styles.mutedText}>Tidak ada action item.</Text>}
        </>
      );
    },
  },
];

// Kartu A dan B berdampingan; barisnya meregang supaya kedua kartu sama tinggi.
export function CompareRow({ section, left, right }) {
  const cell = (state) => {
    const meeting = state.data;
    const summary = meeting?.summary;
    if (state.status !== "done") return <View style={styles.col} />;
    return (
      <View style={styles.col}>
        <SectionCard icon={section.icon} title={section.title} count={summary && section.count ? section.count(summary) : null}>
          {summary ? section.body(summary, meeting) : <Text style={styles.mutedText}>Rapat ini belum punya ringkasan.</Text>}
        </SectionCard>
      </View>
    );
  };
  return (
    <View style={styles.grid}>
      {cell(left)}
      {cell(right)}
    </View>
  );
}
