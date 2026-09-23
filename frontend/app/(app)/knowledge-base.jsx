import { Feather } from "@expo/vector-icons";
import { Link } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { searchKnowledgeBase } from "@/lib/api";
import { formatMeetingDate, PLATFORM_LABEL } from "@/lib/format";

// Search-only, deliberately no chat/conversation UI — the advisor's explicit
// direction was a RAG knowledge base people *search*, not a standing
// chatbot (see CLAUDE.md). A query goes straight to GET
// /knowledge-base/search and comes back as a ranked list of matched summary
// chunks; there's no GPT call and no message history anywhere here — the
// "Hasil Lintas Rapat" card below is worded to match that (no claim of an
// AI-synthesized answer, just relevant chunks pooled across meetings).
const KIND_LABEL = {
  executive_summary: "Ringkasan",
  key_decision: "Keputusan",
  topic: "Topik",
  action_item: "Action Item",
};
const KIND_COLOR = {
  executive_summary: colors.info,
  key_decision: colors.success,
  topic: colors.goldDeep,
  action_item: colors.danger,
};

const EXAMPLE_QUERIES = [
  "Keputusan penting minggu ini",
  "Siapa yang bertanggung jawab atas testing?",
  "Progress fitur RAG",
  "Masalah yang dilaporkan soal speaker detection",
];

const FEATURES = [
  {
    icon: "search",
    color: colors.info,
    title: "Pencarian Semantik",
    description: "Temukan informasi dari seluruh rapat menggunakan bahasa natural, bukan sekadar kata kunci.",
  },
  {
    icon: "layers",
    color: colors.success,
    title: "Hasil Lintas Rapat",
    description: "Cuplikan paling relevan dikumpulkan dari semua rapat sekaligus, diurutkan berdasarkan relevansi.",
  },
  {
    icon: "link",
    color: colors.goldDeep,
    title: "Sumber Transparan",
    description: "Setiap hasil pencarian tertaut langsung ke rapat aslinya — tidak ada jawaban tanpa sumber.",
  },
];

function ResultCard({ result }) {
  const { date, time } = formatMeetingDate(result.meeting_created_at);
  const kindColor = KIND_COLOR[result.kind] || colors.inkFaint;
  return (
    <Link href={`/rapat/${result.meeting_id}`} asChild>
      <Pressable style={styles.card}>
        <View style={styles.cardHeader}>
          <View style={[styles.kindBadge, { backgroundColor: `${kindColor}22` }]}>
            <Text style={[styles.kindBadgeLabel, { color: kindColor }]}>{KIND_LABEL[result.kind] || result.kind}</Text>
          </View>
          <Text style={styles.cardMeta}>
            {result.meeting_title} · {PLATFORM_LABEL[result.meeting_platform] || result.meeting_platform} · {date}, {time}
          </Text>
          <Text style={styles.cardScore}>{Math.round(result.similarity * 100)}% relevan</Text>
        </View>
        <Text style={styles.cardText}>{result.text}</Text>
      </Pressable>
    </Link>
  );
}

export default function KnowledgeBaseScreen() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("idle"); // idle | loading | error | done
  const [answer, setAnswer] = useState(null);
  const [results, setResults] = useState([]);
  const [error, setError] = useState("");

  function runSearch(q) {
    const value = (q ?? query).trim();
    if (!value) return;
    setQuery(value);
    setStatus("loading");
    setError("");
    searchKnowledgeBase(value)
      .then((data) => {
        setAnswer(data.answer);
        setResults(data.results);
        setStatus("done");
      })
      .catch((e) => {
        setError(e.message || "Gagal mencari");
        setStatus("error");
      });
  }

  const showHero = status === "idle";

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        {showHero && (
          <View style={styles.hero}>
            <View style={styles.heroIcon}>
              <Feather name="zap" size={22} color={colors.goldDeep} />
            </View>
            <Text style={styles.heroTitle}>Knowledge Base</Text>
            <Text style={styles.heroSubtitle}>Cari apapun dari seluruh rapat Anda</Text>
          </View>
        )}

        {!showHero && (
          <View style={styles.compactHeader}>
            <Text style={styles.eyebrow}>MENU</Text>
            <Text style={styles.title}>Knowledge Base</Text>
          </View>
        )}

        <View style={styles.searchBar}>
          <Feather name="search" size={16} color={colors.inkFaint} />
          <TextInput
            style={styles.searchInput}
            placeholder="Contoh: Apa keputusan dari rapat minggu lalu?"
            placeholderTextColor={colors.inkFaint}
            value={query}
            onChangeText={setQuery}
            onSubmitEditing={() => runSearch()}
            returnKeyType="search"
          />
          <Pressable style={styles.searchButton} onPress={() => runSearch()} disabled={status === "loading" || !query.trim()}>
            {status === "loading" ? (
              <ActivityIndicator color={colors.ink} size="small" />
            ) : (
              <Text style={styles.searchButtonLabel}>Cari</Text>
            )}
          </Pressable>
        </View>

        {showHero && (
          <>
            <View style={styles.exampleRow}>
              {EXAMPLE_QUERIES.map((q) => (
                <Pressable key={q} style={styles.exampleChip} onPress={() => runSearch(q)}>
                  <Text style={styles.exampleChipLabel}>{q}</Text>
                </Pressable>
              ))}
            </View>

            <View style={styles.featureRow}>
              {FEATURES.map((f) => (
                <View key={f.title} style={styles.featureCard}>
                  <View style={[styles.featureIcon, { backgroundColor: `${f.color}1A` }]}>
                    <Feather name={f.icon} size={16} color={f.color} />
                  </View>
                  <Text style={styles.featureTitle}>{f.title}</Text>
                  <Text style={styles.featureDescription}>{f.description}</Text>
                </View>
              ))}
            </View>
          </>
        )}

        {status === "error" && (
          <View style={styles.stateBox}>
            <Feather name="alert-circle" size={20} color={colors.danger} />
            <Text style={styles.stateText}>{error}</Text>
          </View>
        )}

        {status === "done" && results.length === 0 && (
          <View style={styles.stateBox}>
            <Feather name="inbox" size={20} color={colors.inkFaint} />
            <Text style={styles.stateText}>Tidak ada hasil yang cukup relevan untuk pencarian ini.</Text>
          </View>
        )}

        {status === "done" && results.length > 0 && (
          <>
            {answer && (
              <View style={styles.answerBox}>
                <View style={styles.answerHeader}>
                  <Feather name="zap" size={14} color={colors.goldDeep} />
                  <Text style={styles.answerLabel}>Jawaban</Text>
                </View>
                <Text style={styles.answerText}>{answer}</Text>
              </View>
            )}
            <Text style={styles.sourcesLabel}>Sumber</Text>
            <View style={styles.results}>
              {results.map((r, i) => (
                <ResultCard key={`${r.meeting_id}-${r.kind}-${i}`} result={r} />
              ))}
            </View>
          </>
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { alignItems: "center", padding: spacing.xxl },
  content: { gap: spacing.md, maxWidth: 900, width: "100%" },

  hero: { alignItems: "center", gap: 6, marginBottom: spacing.sm },
  heroIcon: {
    width: 44,
    height: 44,
    borderRadius: radius.pill,
    backgroundColor: colors.goldSoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 4,
  },
  heroTitle: { ...type.display, color: colors.ink, textAlign: "center" },
  heroSubtitle: { ...type.body, color: colors.inkSoft, textAlign: "center" },

  compactHeader: { marginBottom: spacing.xs },
  eyebrow: { ...type.eyebrow, color: colors.inkFaint },
  title: { ...type.display, color: colors.ink, marginTop: 4 },

  searchBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 4,
    ...shadow.card,
  },
  searchInput: { ...type.body, color: colors.ink, flex: 1, paddingVertical: 10, outlineStyle: "none" },
  searchButton: {
    backgroundColor: colors.gold,
    paddingVertical: 9,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.sm,
    minWidth: 64,
    alignItems: "center",
  },
  searchButtonLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },

  exampleRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, justifyContent: "center", marginTop: spacing.xs },
  exampleChip: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    paddingVertical: 7,
    paddingHorizontal: spacing.md,
  },
  exampleChipLabel: { ...type.small, color: colors.inkSoft },

  featureRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: spacing.lg },
  featureCard: {
    flex: 1,
    minWidth: 220,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: 4,
    ...shadow.card,
  },
  featureIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.sm,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 4,
  },
  featureTitle: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },
  featureDescription: { ...type.small, color: colors.inkSoft, lineHeight: 18 },

  stateBox: { alignItems: "center", gap: spacing.sm, padding: spacing.xxl },
  stateText: { ...type.body, color: colors.inkSoft, textAlign: "center" },

  answerBox: {
    backgroundColor: colors.goldSoft,
    borderWidth: 1,
    borderColor: colors.gold,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: 6,
    marginTop: spacing.sm,
  },
  answerHeader: { flexDirection: "row", alignItems: "center", gap: 6 },
  answerLabel: { ...type.small, fontWeight: "700", color: colors.goldDeep },
  answerText: { ...type.body, color: colors.ink, lineHeight: 21 },
  sourcesLabel: { ...type.eyebrow, color: colors.inkFaint, marginTop: spacing.sm },

  results: { gap: spacing.sm },
  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: 6,
    ...shadow.card,
  },
  cardHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" },
  kindBadge: { borderRadius: radius.pill, paddingVertical: 2, paddingHorizontal: 8 },
  kindBadgeLabel: { ...type.small, fontWeight: "700" },
  cardMeta: { ...type.small, color: colors.inkFaint },
  cardScore: { ...type.small, color: colors.inkFaint, marginLeft: "auto", fontVariant: ["tabular-nums"] },
  cardText: { ...type.body, color: colors.ink, lineHeight: 21 },
});
