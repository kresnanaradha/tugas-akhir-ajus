import { Feather } from "@expo/vector-icons";
import { Link, router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { getBillingStatus, listMeetings, searchKnowledgeBase, setKnowledgeBase } from "@/lib/api";
import { formatMeetingDate, PLATFORM_LABEL } from "@/lib/format";

// hanya pencarian, tanpa chat: dosen ingin RAG knowledge base yang dicari orang, bukan chatbot. Query masuk ke
// GET /knowledge-base/search dan kembali sebagai satu jawaban singkat plus potongan ringkasan yang cocok, tanpa riwayat
const KIND_LABEL = {
  executive_summary: "Pokok Pembahasan",
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
    description: "Setiap hasil pencarian tertaut langsung ke rapat aslinya, tidak ada jawaban tanpa sumber.",
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

function KbMeetingRow({ meeting, onRemove }) {
  const { date, time } = formatMeetingDate(meeting.created_at);
  return (
    <View style={styles.kbRow}>
      <Link href={`/rapat/${meeting.id}`} asChild>
        <Pressable style={{ flex: 1 }}>
          <Text style={styles.kbRowTitle} numberOfLines={1}>{meeting.title}</Text>
          <Text style={styles.cardMeta}>
            {PLATFORM_LABEL[meeting.platform] || meeting.platform} · {date}, {time}
          </Text>
        </Pressable>
      </Link>
      <Pressable style={styles.kbRemove} onPress={() => onRemove(meeting.id)} hitSlop={6}>
        <Feather name="x" size={13} color={colors.inkSoft} />
        <Text style={styles.kbRemoveLabel}>Keluarkan</Text>
      </Pressable>
    </View>
  );
}

export default function KnowledgeBaseScreen() {
  const [kbMeetings, setKbMeetings] = useState(null); // null = memuat
  const [plan, setPlan] = useState(null); // null = memuat; Free tidak punya Knowledge Base (backend juga 402)
  useEffect(() => {
    getBillingStatus().then((s) => setPlan(s.plan)).catch(() => setPlan("unknown"));
  }, []);

  // Ambil ulang tiap kali fokus supaya rapat yang ditambahkan dari halamannya sendiri muncul di sini.
  useFocusEffect(
    useCallback(() => {
      listMeetings()
        .then((all) => setKbMeetings(all.filter((m) => m.in_kb)))
        .catch(() => setKbMeetings([]));
    }, [])
  );

  function removeFromKb(id) {
    setKbMeetings((list) => list.filter((m) => m.id !== id));
    setKnowledgeBase(id, false).catch(() =>
      listMeetings().then((all) => setKbMeetings(all.filter((m) => m.in_kb))).catch(() => {})
    );
  }

  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("idle"); // idle | loading | error | done
  const [answer, setAnswer] = useState(null);
  const [results, setResults] = useState([]);
  const [error, setError] = useState("");

  // supaya pencarian di TopBar (atau tautan apa pun) bisa membuka pencarian lewat /knowledge-base?q=...
  const { q: initialQuery } = useLocalSearchParams();
  useEffect(() => {
    if (initialQuery) runSearch(String(initialQuery));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialQuery]);

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

  if (plan === null) {
    return <ActivityIndicator style={{ marginTop: spacing.xxl }} color={colors.gold} />;
  }
  if (plan === "free") {
    return (
      <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
        <View style={[styles.content, { maxWidth: 560, alignItems: "center", paddingVertical: spacing.xxl }]}>
          <View style={{ width: 56, height: 56, borderRadius: 28, backgroundColor: colors.goldSoft || colors.surface, alignItems: "center", justifyContent: "center" }}>
            <Feather name="lock" size={24} color={colors.goldDeep} />
          </View>
          <Text style={[styles.title, { textAlign: "center" }]}>Knowledge Base adalah fitur Pro</Text>
          <Text style={[styles.heroSubtitle, { textAlign: "center" }]}>
            Cari keputusan, topik, dan action item dari semua rapat lama dengan bahasa biasa, lengkap dengan sumber rapatnya. Upgrade ke Pro (Rp99rb / bulan) untuk membukanya, plus rapat dan durasi rekaman tanpa batas.
          </Text>
          <Pressable style={styles.searchButton} onPress={() => router.push("/billing")}>
            <Text style={styles.searchButtonLabel}>Upgrade ke Pro</Text>
          </Pressable>
        </View>
      </ScrollView>
    );
  }

  const kbCard = (
            <View style={styles.sideCard}>
        <Text style={styles.sourcesLabel}>RAPAT DI KNOWLEDGE BASE{kbMeetings ? ` (${kbMeetings.length})` : ""}</Text>
        {kbMeetings && kbMeetings.length === 0 && (
          <Text style={styles.cardMeta}>
            Belum ada. Buka detail rapat lalu klik "Simpan ke Knowledge Base" (hanya ringkasan dan keputusan utama yang disimpan).
          </Text>
        )}
        {kbMeetings && kbMeetings.length > 0 && (
          <View style={styles.results}>
            {kbMeetings.map((m) => (
              <KbMeetingRow key={m.id} meeting={m} onRemove={removeFromKb} />
            ))}
          </View>
        )}

            </View>
  );

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <View>
          <Text style={styles.title}>Knowledge Base</Text>
          <Text style={styles.heroSubtitle}>Cari apapun dari rapat yang sudah Anda simpan ke Knowledge Base.</Text>
        </View>

        <View style={styles.split}>
          <View style={styles.mainCol}>
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
              </>
            )}

            {showHero && kbCard}

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

          <View style={styles.sideCol}>
            {!showHero && kbCard}
            {showHero && (
              <View style={styles.sideCard}>
                <Text style={styles.sourcesLabel}>CARA KERJA</Text>
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
              </View>
            )}
          </View>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { alignItems: "center", paddingVertical: spacing.lg, paddingHorizontal: "5%" },
  content: { gap: spacing.md, width: "100%" },

  split: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, alignItems: "flex-start" },
  mainCol: { flex: 1.6, minWidth: 420, gap: spacing.md },
  sideCol: { flex: 1, minWidth: 300, gap: spacing.md },
  sideCard: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
    ...shadow.card,
  },
  heroSubtitle: { ...type.body, color: colors.inkSoft, marginTop: 2 },

  title: { ...type.h1, fontSize: 24, color: colors.ink, marginTop: 4 },

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

  exampleRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs },
  exampleChip: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    paddingVertical: 7,
    paddingHorizontal: spacing.md,
  },
  exampleChipLabel: { ...type.small, color: colors.inkSoft },

  featureRow: { gap: spacing.md },
  featureCard: { gap: 2 },
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

  stateBox: { alignItems: "center", gap: spacing.sm, padding: spacing.xl },
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
  kbRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  kbRowTitle: { ...type.bodyMedium, fontWeight: "600", color: colors.ink },
  kbRemove: { flexDirection: "row", alignItems: "center", gap: 4 },
  kbRemoveLabel: { ...type.small, color: colors.inkSoft },
  cardText: { ...type.body, color: colors.ink, lineHeight: 21 },
});
