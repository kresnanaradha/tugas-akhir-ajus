// Fungsi bantu halaman detail rapat: baris transkrip, warna pembicara, dan angka di atas tab.

import { colors } from "@/constants/theme";

// Satu warna per pembicara, dipilih dari tema. Seluruh label di-hash (bukan hanya angka SPEAKER_00), jadi
// pembicara yang diganti nama ("Kresna") tetap berwarna sama dan dua label yang digabung jadi satu nama berwarna sama.
const SPEAKER_PALETTE = [colors.info, colors.success, colors.goldDeep, colors.danger];
export function speakerColor(speaker) {
  if (!speaker) return SPEAKER_PALETTE[0];
  let hash = 0;
  for (let i = 0; i < speaker.length; i++) hash = (hash * 31 + speaker.charCodeAt(i)) >>> 0;
  return SPEAKER_PALETTE[hash % SPEAKER_PALETTE.length];
}

// transkrip adalah satu baris "[SPEAKER_NN] teks" per ucapan. Baris yang tidak cocok (kosong, format lama) tidak punya pembicara
const LINE_PATTERN = /^\[(.+?)\]\s?(.*)$/;
export function parseTranscriptLines(text) {
  return (text || "").split("\n").map((line) => {
    const match = LINE_PATTERN.exec(line);
    return match ? { speaker: match[1], text: match[2] } : { speaker: null, text: line };
  });
}

// pembicara yang ditampilkan tiap baris: ganti nama untuk baris itu saja (diarization menaruhnya di orang yang salah) menang atas
// ganti nama seluruh id pembicara (SPEAKER_00 -> "Kresna"), yang menang atas id itu sendiri. null untuk baris tanpa pembicara
export function resolveLineSpeakers(lines, speakerNames, lineOverrides) {
  return lines.map((l, i) => (l.speaker ? lineOverrides[i] || speakerNames[l.speaker] || l.speaker : null));
}

export function joinTranscriptLines(lines, lineSpeakers) {
  return lines.map((l, i) => (lineSpeakers[i] ? `[${lineSpeakers[i]}] ${l.text}` : l.text)).join("\n");
}

// Editor mulai dari transkrip mentah, tapi menyimpan juga menulis nama pilihan dan teks yang diedit ke segments.json
// (urutan baris sama). Bangun editor dari situ supaya nama dan edit yang tersimpan selamat setelah reload: per id pembicara
// nama tersimpan yang paling umum adalah penggantian nama, dan baris yang berbeda darinya menjadi penggantian per baris.
export function buildEditorState(meeting) {
  let lines = parseTranscriptLines(meeting.transcript);
  const names = {};
  const overrides = {};
  const segs = meeting.segments;
  if (segs && segs.length === lines.length) {
    const counts = {};
    lines.forEach((l, i) => {
      if (!l.speaker) return;
      const n = segs[i].speaker || l.speaker;
      counts[l.speaker] = counts[l.speaker] || {};
      counts[l.speaker][n] = (counts[l.speaker][n] || 0) + 1;
    });
    for (const raw of Object.keys(counts)) {
      const [best] = Object.entries(counts[raw]).sort((a, b) => b[1] - a[1])[0];
      if (best !== raw) names[raw] = best;
    }
    lines.forEach((l, i) => {
      if (!l.speaker) return;
      const n = segs[i].speaker || l.speaker;
      if (n !== (names[l.speaker] || l.speaker)) overrides[i] = n;
    });
    lines = lines.map((l, i) => ({ ...l, text: segs[i].text ?? l.text }));
  }
  return { lines, names, overrides };
}

// angka di atas tab, dihitung dari yang sudah dimiliki halaman
export function meetingStats(meeting) {
  const text = meeting.fixed_transcript || meeting.transcript || "";
  const items = meeting.summary?.action_items || [];
  const speakers = new Set((meeting.segments || []).map((seg) => seg.speaker).filter(Boolean));
  return {
    words: text.trim() ? text.trim().split(/\s+/).length : 0,
    speakerCount: speakers.size || new Set(text.match(/^\[(.+?)\]/gm) || []).size,
    actionTotal: items.length,
    actionDone: items.filter((i) => i.done).length,
    decisions: meeting.summary?.key_decisions?.length || 0,
  };
}

export function formatBytes(bytes) {
  if (bytes == null) return null;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatElapsed(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}
