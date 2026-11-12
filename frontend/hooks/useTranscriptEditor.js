import { useState } from "react";

import { updateTranscript } from "@/lib/api";
import { buildEditorState, joinTranscriptLines, resolveLineSpeakers } from "@/lib/transcript";

// state tab Edit Transkrip. Dipakai di halaman, bukan di dalam tab, supaya editan yang belum disimpan tidak hilang saat
// pindah tab. load() mengembalikan editor ke isi rapat yang tersimpan
export function useTranscriptEditor(id, setMeeting) {
  // Tab Edit Transkrip: transkrip mentah sebagai baris yang bisa diedit (kiri) dengan versi perbaikan AI sebagai acuan (kanan)
  const [editedLines, setEditedLines] = useState([]);
  // { SPEAKER_00: "Kresna" }: mengganti nama pembicara di mana-mana, berkunci id aslinya supaya warna badge tetap
  const [speakerNames, setSpeakerNames] = useState({});
  // { <indeks baris>: "Diva" }: memindahkan satu baris ke pembicara lain, saat diarization salah hanya di baris itu
  const [lineOverrides, setLineOverrides] = useState({});
  const [savingTranscript, setSavingTranscript] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [savedNotice, setSavedNotice] = useState(false);
  // Edit (nama, baris dipindah, teks) yang belum disimpan: ringkasan hanya berubah saat disimpan.
  const [dirty, setDirty] = useState(false);

  function load(data) {
    const editor = buildEditorState(data);
    setEditedLines(editor.lines);
    setSpeakerNames(editor.names);
    setLineOverrides(editor.overrides);
  }

  async function handleSaveTranscript() {
    setSavingTranscript(true);
    setSaveError("");
    setSavedNotice(false);
    try {
      // ringkasan dibuat ulang dari transkrip yang baru dikoreksi user
      const lineSpeakers = resolveLineSpeakers(editedLines, speakerNames, lineOverrides);
      const result = await updateTranscript(
        id,
        joinTranscriptLines(editedLines, lineSpeakers),
        lineSpeakers,
        editedLines.map((l) => l.text)
      );
      setMeeting((m) => ({
        ...m,
        fixed_transcript: result.fixed_transcript,
        segments: result.segments ?? m.segments,
        summary: result.summary ?? null,
        summary_error: result.summary_error,
      }));
      setSavedNotice(true);
      setDirty(false);
    } catch (e) {
      setSaveError(e.message || "Gagal menyimpan transkrip");
    } finally {
      setSavingTranscript(false);
    }
  }

  return {
    editedLines, setEditedLines, speakerNames, setSpeakerNames, lineOverrides, setLineOverrides,
    savingTranscript, saveError, savedNotice, dirty, setDirty, load, handleSaveTranscript,
  };
}
