import { Feather } from "@expo/vector-icons";
import { useState } from "react";
import { Pressable, Text, TextInput, useWindowDimensions, View } from "react-native";

import { colors, spacing } from "@/constants/theme";
import { generateShortSummary, replaceActionItems, setKnowledgeBase, toggleActionItem } from "@/lib/api";

import { styles } from "./styles";

const POKOK_LINES = 9; // baris yang tampil saat diciutkan kalau tinggi kolom kiri belum terukur (layar sempit)
const POKOK_LONG_CHARS = 900; // di bawah ini teksnya pendek, tombol tidak perlu
const POKOK_LINE_HEIGHT = 21; // sama dengan lineHeight styles.summaryText
// tinggi kartu di luar teksnya: padding atas bawah + border + ikon header + jarak + tombol + jarak
const POKOK_CHROME = spacing.lg * 2 + 2 + 30 + spacing.sm + 18 + spacing.sm;

// tab Pokok Pembahasan Rapat: ringkasan (dan tombol Knowledge Base), pokok pembahasan, topik, keputusan utama, dan
// action item yang bisa dicentang, diubah, ditambah, dan dihapus
export function RingkasanTab({ id, meeting, setMeeting, canEdit }) {
  // layar lebar: topik, keputusan, dan action item di kiri, ringkasan di kanan. Layar sempit ditumpuk, ringkasan dulu
  const wideSummary = useWindowDimensions().width >= 1100;
  // Pokok Pembahasan bisa sangat panjang dan menarik kolom kiri jadi kosong, jadi diciutkan dulu
  const [pokokOpen, setPokokOpen] = useState(false);
  const pokokLong = (meeting?.summary?.executive_summary || "").length > POKOK_LONG_CHARS;
  // layar lebar: terciut sampai dasar kartunya sejajar dengan dasar kolom kiri (Action Items)
  const [sideH, setSideH] = useState(0);
  const [ringH, setRingH] = useState(0);
  const pokokLines =
    wideSummary && sideH && ringH
      ? Math.max(4, Math.floor((sideH - ringH - spacing.md - POKOK_CHROME) / POKOK_LINE_HEIGHT))
      : POKOK_LINES;
  const [kbSaving, setKbSaving] = useState(false);
  const [kbError, setKbError] = useState("");
  const [shortBusy, setShortBusy] = useState(false);
  const [shortError, setShortError] = useState("");
  // Editor action item: item mana yang sedang diedit (indeks, "new", atau null) + drafnya.
  const [editingItem, setEditingItem] = useState(null);
  const [itemDraft, setItemDraft] = useState({ task: "", assignee: "", due: "" });
  const [itemSaving, setItemSaving] = useState(false);
  const [itemError, setItemError] = useState("");

  function handleToggleActionItem(index) {
    // optimistis, dan state lokal menang: permintaan membawa nilai yang diinginkan dan responsnya diabaikan (bisa lebih lama
    // dari klik berikutnya), jadi centang cepat berturut-turut tidak saling membatalkan. Hanya item ini yang dikembalikan kalau gagal
    const done = !meeting.summary.action_items[index].done;
    const setDone = (value) =>
      setMeeting((m) => ({
        ...m,
        summary: {
          ...m.summary,
          action_items: m.summary.action_items.map((item, i) => (i === index ? { ...item, done: value } : item)),
        },
      }));
    setDone(done);
    toggleActionItem(id, index, done).catch(() => setDone(!done));
  }

  function startEditItem(index) {
    const item = index === "new" ? {} : meeting.summary.action_items[index];
    setItemDraft({ task: item.task || "", assignee: item.assignee || "", due: item.due || "" });
    setItemError("");
    setEditingItem(index);
  }

  async function saveItems(items) {
    setItemSaving(true);
    setItemError("");
    try {
      const summary = await replaceActionItems(id, items);
      setMeeting((m) => ({ ...m, summary }));
      setEditingItem(null);
    } catch (e) {
      setItemError(e.message || "Gagal menyimpan action item");
    } finally {
      setItemSaving(false);
    }
  }

  function handleSaveItem() {
    if (!itemDraft.task.trim()) {
      setItemError("Isi tugas tidak boleh kosong");
      return;
    }
    const items = [...(meeting.summary.action_items || [])];
    if (editingItem === "new") items.push({ ...itemDraft, done: false });
    else items[editingItem] = { ...items[editingItem], ...itemDraft };
    saveItems(items);
  }

  function handleRemoveItem(index) {
    saveItems(meeting.summary.action_items.filter((_, i) => i !== index));
  }

  function renderItemForm(index) {
    return (
      <View key={index} style={styles.itemForm}>
        <TextInput
          style={styles.itemInput}
          value={itemDraft.task}
          onChangeText={(task) => setItemDraft((d) => ({ ...d, task }))}
          placeholder="Tugas"
          placeholderTextColor={colors.inkFaint}
          multiline
        />
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          <TextInput
            style={[styles.itemInput, { flex: 1 }]}
            value={itemDraft.assignee}
            onChangeText={(assignee) => setItemDraft((d) => ({ ...d, assignee }))}
            placeholder="Penanggung jawab"
            placeholderTextColor={colors.inkFaint}
          />
          <TextInput
            style={[styles.itemInput, { flex: 1 }]}
            value={itemDraft.due}
            onChangeText={(due) => setItemDraft((d) => ({ ...d, due }))}
            placeholder="Tenggat"
            placeholderTextColor={colors.inkFaint}
          />
        </View>
        {!!itemError && <Text style={styles.errorText}>{itemError}</Text>}
        <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center" }}>
          <Pressable style={[styles.smallButton, styles.smallButtonPrimary]} onPress={handleSaveItem} disabled={itemSaving}>
            <Text style={styles.smallButtonLabel}>{itemSaving ? "Menyimpan..." : "Simpan"}</Text>
          </Pressable>
          <Pressable style={styles.smallButton} onPress={() => setEditingItem(null)} disabled={itemSaving}>
            <Text style={styles.smallButtonLabel}>Batal</Text>
          </Pressable>
          {index !== "new" && (
            <Pressable style={{ marginLeft: "auto" }} onPress={() => handleRemoveItem(index)} disabled={itemSaving}>
              <Text style={[styles.smallButtonLabel, { color: colors.danger }]}>Hapus</Text>
            </Pressable>
          )}
        </View>
      </View>
    );
  }

  async function handleShortSummary() {
    setShortBusy(true);
    setShortError("");
    try {
      const summary = await generateShortSummary(id);
      setMeeting((m) => ({ ...m, summary }));
    } catch (e) {
      setShortError(e.message || "Gagal membuat ringkasan");
    } finally {
      setShortBusy(false);
    }
  }

  function handleToggleKb() {
    const enabled = !meeting.in_kb;
    setKbSaving(true);
    setKbError("");
    setKnowledgeBase(id, enabled)
      .then(() => setMeeting((m) => ({ ...m, in_kb: enabled })))
      .catch((e) => setKbError(e.message || "Gagal memperbarui Knowledge Base"))
      .finally(() => setKbSaving(false));
  }

  return (
    (meeting.summary ? (
      <View style={styles.section}>
        {/* row-reverse: kolom pertama di JSX (ringkasan) jatuh di kanan, kolom kedua (topik dkk) di kiri */}
        <View style={[styles.summaryGrid, wideSummary && styles.summaryGridWide]}>
        <View style={[styles.summaryMain, wideSummary && { flex: 3 }]}>
        <View style={styles.summaryCard} onLayout={(e) => setRingH(e.nativeEvent.layout.height)}>
          <View style={styles.summaryCardHeader}>
            <View style={styles.iconWrap}>
              <Feather name="file-text" size={16} color={colors.goldDeep} />
            </View>
            <Text style={[styles.summaryCardLabel, { flex: 1 }]}>Ringkasan</Text>
            {canEdit && (
              <Pressable
                style={[styles.kbButton, meeting.in_kb && styles.kbButtonOn]}
                onPress={handleToggleKb}
                disabled={kbSaving}
              >
                <Feather name={meeting.in_kb ? "check" : "plus"} size={13} color={colors.ink} />
                <Text style={styles.kbButtonLabel}>
                  {kbSaving ? "Menyimpan..." : meeting.in_kb ? "Ada di Knowledge Base" : "Simpan ke Knowledge Base"}
                </Text>
              </Pressable>
            )}
          </View>
          {!!kbError && <Text style={[styles.errorText, { marginBottom: spacing.sm }]}>{kbError}</Text>}
          {meeting.summary.short_summary ? (
            <Text style={styles.summaryText}>{meeting.summary.short_summary}</Text>
          ) : (
            <View style={{ gap: spacing.sm, alignItems: "flex-start" }}>
              <Text style={styles.actionItemMeta}>Rapat ini diringkas sebelum ringkasan singkat ada.</Text>
              {canEdit && (
                <Pressable style={styles.smallButton} onPress={handleShortSummary} disabled={shortBusy}>
                  <Feather name="zap" size={12} color={colors.ink} />
                  <Text style={styles.smallButtonLabel}>{shortBusy ? "Membuat..." : "Buat ringkasan singkat"}</Text>
                </Pressable>
              )}
              {!!shortError && <Text style={styles.errorText}>{shortError}</Text>}
            </View>
          )}
        </View>

        <View style={[styles.summaryCard, wideSummary && { flex: 1 }]}>
          <View style={styles.summaryCardHeader}>
            <View style={styles.iconWrap}>
              <Feather name="zap" size={16} color={colors.goldDeep} />
            </View>
            <Text style={[styles.summaryCardLabel, { flex: 1 }]}>Pokok Pembahasan Rapat</Text>
          </View>
          <Text style={styles.summaryText} numberOfLines={pokokOpen || !pokokLong ? undefined : pokokLines}>
            {meeting.summary.executive_summary}
          </Text>
          {pokokLong && (
            <Pressable style={styles.expandButton} onPress={() => setPokokOpen((v) => !v)}>
              <Text style={styles.expandLabel}>{pokokOpen ? "Ciutkan" : "Lihat selengkapnya"}</Text>
              <Feather name={pokokOpen ? "chevron-up" : "chevron-down"} size={14} color={colors.goldDeep} />
            </Pressable>
          )}
        </View>

        </View>

        <View
          style={[styles.summarySide, wideSummary && { flex: 2, alignSelf: "flex-start" }]}
          onLayout={(e) => setSideH(e.nativeEvent.layout.height)}
        >
        <View style={styles.sideCard}>
          <Text style={styles.colTitle}>Topik Dibahas</Text>
          {meeting.summary.topics_discussed?.map((t, i) => (
            <View key={i} style={styles.topicRow}>
              <Text style={styles.topicIndex}>{i + 1}</Text>
              <Text style={styles.topicText}>{t}</Text>
            </View>
          ))}
        </View>
        <View style={styles.sideCard}>
          <Text style={styles.colTitle}>Keputusan Utama</Text>
          {meeting.summary.key_decisions?.map((d, i) => (
            <View key={i} style={styles.decisionRow}>
              <Feather name="check-circle" size={14} color={colors.success} />
              <Text style={styles.decisionText}>{d}</Text>
            </View>
          ))}
        </View>

        <View style={styles.actionItemsCard}>
          <View style={styles.actionItemsHeader}>
            <Text style={[styles.colTitle, { flex: 1 }]}>Action Items</Text>
            {editingItem !== "new" && canEdit && (
              <Pressable style={styles.smallButton} onPress={() => startEditItem("new")}>
                <Feather name="plus" size={12} color={colors.ink} />
                <Text style={styles.smallButtonLabel}>Tambah</Text>
              </Pressable>
            )}
          </View>
          {!meeting.summary.action_items?.length && editingItem !== "new" && (
            <Text style={styles.actionItemMeta}>Belum ada action item.</Text>
          )}
          {meeting.summary.action_items?.map((item, i) =>
            editingItem === i ? (
              renderItemForm(i)
            ) : (
              <View key={i} style={styles.actionItemRow}>
                {/* seluruh sisi kiri (kotak centang dan teks) bisa diketuk, ikon kecil saja mudah terlewat */}
                <Pressable style={styles.actionItemMain} onPress={() => canEdit && handleToggleActionItem(i)}>
                  <Feather
                    name={item.done ? "check-square" : "square"}
                    size={15}
                    color={item.done ? colors.success : colors.inkFaint}
                    style={{ marginTop: 2 }}
                  />
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.actionItemTask, item.done && styles.actionItemTaskDone]}>
                      {item.task}
                    </Text>
                    {(item.assignee || item.due) && (
                      <Text style={styles.actionItemMeta}>
                        {[item.assignee, item.due].filter(Boolean).join(" · ")}
                      </Text>
                    )}
                  </View>
                </Pressable>
                {canEdit && (
                  <Pressable onPress={() => startEditItem(i)} hitSlop={10}>
                    <Feather name="edit-2" size={13} color={colors.inkFaint} style={{ marginTop: 3 }} />
                  </Pressable>
                )}
              </View>
            )
          )}
          {editingItem === "new" && renderItemForm("new")}
        </View>
        </View>
        </View>
      </View>
    ) : (
      <View style={styles.section}>
        <Text style={styles.errorText}>Ringkasan gagal: {meeting.summary_error || "tidak diketahui"}.</Text>
      </View>
))
  );
}
