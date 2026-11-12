import { Feather } from "@expo/vector-icons";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, TextInput, View } from "react-native";

import { colors, radius } from "@/constants/theme";
import { getRecordingUrl } from "@/lib/api";
import { formatElapsed, parseTranscriptLines, resolveLineSpeakers, speakerColor } from "@/lib/transcript";

import { SpeakerBadge } from "./SpeakerBadge";
import { styles } from "./styles";

// <textarea> mentah (hanya web) yang tumbuh sesuai teksnya: TextInput multiline RN selalu menyisakan dua baris, yang meninggalkan
// celah di bawah setiap baris satu garis
function LineTextarea({ value, onChange, onFocus }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);
  return (
    <textarea
      ref={ref}
      rows={1}
      value={value}
      onFocus={onFocus}
      onChange={(e) => onChange(e.target.value)}
      style={{
        width: "100%",
        boxSizing: "border-box",
        border: "none",
        outline: "none",
        resize: "none",
        overflow: "hidden",
        background: "transparent",
        padding: 0,
        margin: 0,
        display: "block",
        fontFamily: 'System, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
        fontSize: 14,
        lineHeight: "20px",
        color: colors.ink,
      }}
    />
  );
}

// satu baris panel nama pembicara: mengganti nama id pembicara di mana-mana. Menyimpan draf dan menyimpan saat blur atau enter, jadi
// baris tidak berubah saat mengetik. Kosong = kembali ke id mentah
function SpeakerNameRow({ raw, name, onCommit }) {
  const [draft, setDraft] = useState(name);
  useEffect(() => setDraft(name), [name]);
  const commit = () => onCommit(draft.trim());
  const color = speakerColor(raw);
  return (
    <View style={styles.nameCell}>
      <View style={styles.nameCellLabel}>
        <View style={[styles.mergeMenuDot, { backgroundColor: color }]} />
        <Text style={[styles.nameCellRaw, { color }]}>{raw}</Text>
      </View>
      <TextInput
        style={[styles.nameInput, !!name && styles.nameInputFilled]}
        value={draft}
        placeholder="Nama asli"
        placeholderTextColor={colors.inkFaint}
        onChangeText={setDraft}
        onBlur={commit}
        onSubmitEditing={commit}
      />
    </View>
  );
}

// badge per baris: klik untuk memindahkan hanya baris ini ke pembicara lain. Mengganti nama satu pembicara penuh dilakukan di panel di atas
function LineSpeakerBadge({ raw, value, overridden, options, open, onToggle, onPick, onReset }) {
  const color = speakerColor(overridden ? value : raw);
  return (
    <View style={styles.speakerBadgeWrap}>
      <Pressable onPress={onToggle} style={[styles.speakerBadge, { backgroundColor: `${color}22` }]}>
        <Text style={[styles.speakerBadgeLabel, { color }]}>{value}</Text>
        <Feather name="chevron-down" size={11} color={color} />
      </Pressable>
      {open && (
        <View style={styles.mergeMenu}>
          <Text style={styles.mergeMenuLabel}>Pindahkan baris ini ke:</Text>
          {options.map((label) => (
            <Pressable key={label} style={styles.mergeMenuItem} onPress={() => onPick(label)}>
              <View style={[styles.mergeMenuDot, { backgroundColor: speakerColor(label) }]} />
              <Text style={styles.mergeMenuItemLabel}>{label}</Text>
            </Pressable>
          ))}
          {overridden && (
            <Pressable style={styles.mergeMenuItem} onPress={onReset}>
              <Feather name="rotate-ccw" size={11} color={colors.inkSoft} />
              <Text style={styles.mergeMenuItemLabel}>Kembalikan ke pembicara asli</Text>
            </Pressable>
          )}
        </View>
      )}
    </View>
  );
}

// tab Edit Transkrip: ganti nama pembicara, pindahkan baris ke pembicara lain, ubah teks, lalu simpan dan buat ulang
// ringkasan. State editannya ada di hooks/useTranscriptEditor (dipegang halaman, jadi tidak hilang saat pindah tab)
export function EditorTab({ meeting, editor, videoRef, currentTime, setCurrentTime, seekTo }) {
  const {
    editedLines, setEditedLines, speakerNames, setSpeakerNames, lineOverrides, setLineOverrides,
    savingTranscript, saveError, savedNotice, dirty, setDirty, handleSaveTranscript,
  } = editor;
  // baris yang daftar "pindahkan ke pembicara"-nya terbuka (satu pada satu waktu)
  const [mergeOpenIndex, setMergeOpenIndex] = useState(null);
  // baris yang sedang diedit: "Saran Perbaikan AI" hanya menampilkan versi AI untuk satu baris itu
  const [focusedLineIndex, setFocusedLineIndex] = useState(null);

  // baris tempat video berada (baris dipetakan ke segmen lewat indeks, jadi hanya kalau jumlahnya sama)
  const [playing, setPlaying] = useState(false);
  const editorScrollRef = useRef(null);
  const lineEls = useRef({});
  const activeLine =
    meeting?.segments && meeting.segments.length === editedLines.length
      ? meeting.segments.findIndex((seg) => seg.start != null && currentTime >= seg.start && currentTime < seg.end)
      : -1;
  // Ikuti video hanya saat diputar, supaya tidak pernah berebut dengan user yang mengetik.
  useEffect(() => {
    // Aplikasi web saja: ukur node DOM baris terhadap kotak scroll langsung.
    const box = editorScrollRef.current?.getScrollableNode?.();
    const row = lineEls.current[activeLine];
    if (playing && box && row) {
      const top = row.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop - 40;
      box.scrollTop = Math.max(0, top);
    }
  }, [activeLine, playing]);

  return (
    <View style={styles.section}>
      <View style={styles.editorGrid}>
        <View style={styles.editorCol}>
          <Text style={styles.editorColTitle}>Transkrip Mentah</Text>
          {!!meeting.transcript && (
            <View style={styles.namesPanel}>
              <View style={styles.namesHeader}>
                <Feather name="users" size={14} color={colors.goldDeep} />
                <Text style={styles.namesTitle}>Nama Pembicara</Text>
              </View>
              <Text style={styles.namesHint}>
                Isi nama asli agar tampil di semua baris dan ringkasan setelah disimpan.
              </Text>
              <View style={styles.namesGrid}>
                {[...new Set(editedLines.map((l) => l.speaker).filter(Boolean))].map((raw) => (
                  <SpeakerNameRow
                    key={raw}
                    raw={raw}
                    name={speakerNames[raw] || ""}
                    onCommit={(name) => {
                      if (name !== (speakerNames[raw] || "")) setDirty(true);
                      setSpeakerNames((m) => {
                        const next = { ...m };
                        if (name) next[raw] = name;
                        else delete next[raw];
                        return next;
                      });
                    }}
                  />
                ))}
              </View>
            </View>
          )}
          {meeting.transcript ? (
            <ScrollView ref={editorScrollRef} style={styles.editorLinesBox}>
              {(() => {
                const lineSpeakers = resolveLineSpeakers(editedLines, speakerNames, lineOverrides);
                const rawLabels = [...new Set(editedLines.map((l) => l.speaker).filter(Boolean))];
                const nameOf = (raw) => speakerNames[raw] || raw;
                const pickOptions = [...new Set(rawLabels.map(nameOf))];
                return editedLines.map((line, i) => (
                  <View
                    key={i}
                    style={[
                      styles.editorLineRow,
                      i === activeLine && styles.editorLineRowActive,
                      mergeOpenIndex === i && styles.editorLineRowElevated,
                    ]}
                    ref={(el) => {
                      lineEls.current[i] = el;
                    }}
                  >
                    {line.speaker && (
                      <View style={styles.editorLineHeader}>
                        {meeting.segments?.length === editedLines.length && meeting.segments[i].start != null && (
                          <Pressable onPress={() => seekTo(meeting.segments[i].start)} hitSlop={6}>
                            <Text style={styles.segmentTime}>{formatElapsed(Math.floor(meeting.segments[i].start))}</Text>
                          </Pressable>
                        )}
                        <LineSpeakerBadge
                          raw={line.speaker}
                          value={lineSpeakers[i]}
                          overridden={!!lineOverrides[i]}
                          options={pickOptions.filter((l) => l !== lineSpeakers[i])}
                          open={mergeOpenIndex === i}
                          onToggle={() => setMergeOpenIndex((cur) => (cur === i ? null : i))}
                          onPick={(name) => {
                            setDirty(true);
                            setLineOverrides((m) => {
                              const next = { ...m };
                              if (name === nameOf(line.speaker)) delete next[i];
                              else next[i] = name;
                              return next;
                            });
                            setMergeOpenIndex(null);
                          }}
                          onReset={() => {
                            setDirty(true);
                            setLineOverrides((m) => {
                              const next = { ...m };
                              delete next[i];
                              return next;
                            });
                            setMergeOpenIndex(null);
                          }}
                        />
                      </View>
                    )}
                    <LineTextarea
                      value={line.text}
                      onFocus={() => setFocusedLineIndex(i)}
                      onChange={(text) => {
                        setDirty(true);
                        setEditedLines((lines) => lines.map((l, j) => (j === i ? { ...l, text } : l)));
                      }}
                    />
                  </View>
                ));
              })()}
            </ScrollView>
          ) : (
            <View style={styles.editorRawBox}>
              <Text style={styles.errorText}>
                {meeting.transcript_error ? `Transkrip gagal: ${meeting.transcript_error}.` : "Tidak ada percakapan yang terdeteksi dalam rekaman ini."}
              </Text>
            </View>
          )}
        </View>

        <View style={styles.editorCol}>
          {!!meeting.recording && (
            <video
              ref={videoRef}
              controls
              style={{ width: "100%", borderRadius: radius.md, backgroundColor: "#000", maxHeight: 230, objectFit: "contain", display: "block" }}
              src={getRecordingUrl(meeting.id)}
              onTimeUpdate={(e) => setCurrentTime(e.target.currentTime)}
              onPlay={() => setPlaying(true)}
              onPause={() => setPlaying(false)}
            />
          )}
          <View style={styles.editorColHeader}>
            <Feather name="zap" size={13} color={colors.goldDeep} />
            <Text style={styles.editorColTitle}>Saran Perbaikan AI</Text>
          </View>
          {(() => {
            if (!meeting.fixed_transcript) {
              return (
                <View style={styles.suggestLinesBox}>
                  <Text style={styles.plainTranscript}>Belum ada saran perbaikan.</Text>
                </View>
              );
            }
            if (focusedLineIndex == null) {
              return (
                <View style={styles.suggestLinesBox}>
                  <Text style={styles.plainTranscript}>
                    Klik salah satu baris di Transkrip Mentah untuk melihat saran perbaikan AI-nya di sini.
                  </Text>
                </View>
              );
            }
            // fixed_transcript mempertahankan urutan dan jumlah baris transkrip mentah (perbaikan hanya mengubah kata)
            const suggestedLine = parseTranscriptLines(meeting.fixed_transcript)[focusedLineIndex];
            if (!suggestedLine) {
              return (
                <View style={styles.suggestLinesBox}>
                  <Text style={styles.plainTranscript}>Tidak ada saran untuk baris ini.</Text>
                </View>
              );
            }
            return (
              <View style={styles.suggestLinesBox}>
                <View style={styles.suggestLineRow}>
                  {suggestedLine.speaker && <SpeakerBadge speaker={suggestedLine.speaker} />}
                  <Text style={styles.suggestLineText}>{suggestedLine.text}</Text>
                </View>
              </View>
            );
          })()}
          <View style={styles.editorActions}>
            {dirty && !savingTranscript && (
              <Text style={styles.dirtyNoticeText}>
                Ada perubahan yang belum disimpan. Ringkasan baru ikut berubah setelah kamu klik tombol di bawah.
              </Text>
            )}
            {savedNotice && !dirty && (
              <Text style={styles.savedNoticeText}>Tersimpan, ringkasan diperbarui.</Text>
            )}
            {!!saveError && <Text style={styles.errorText}>{saveError}</Text>}
            <Pressable
              style={[styles.saveButton, savingTranscript && styles.saveButtonDisabled]}
              disabled={savingTranscript || editedLines.every((l) => !l.text.trim())}
              onPress={handleSaveTranscript}
            >
              {savingTranscript ? (
                <ActivityIndicator color={colors.ink} size="small" />
              ) : (
                <Feather name="check" size={13} color={colors.ink} />
              )}
              <Text style={styles.saveButtonLabel}>Simpan & Buat Ulang Ringkasan</Text>
            </Pressable>
          </View>
        </View>
      </View>
    </View>
  );
}
