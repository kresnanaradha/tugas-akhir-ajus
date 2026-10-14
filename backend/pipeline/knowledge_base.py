"""RAG atas ringkasan rapat: query di-embed, Chroma mencari potongan ringkasan terdekat dan GPT-4o mini
menulis satu jawaban singkat dari situ. Sengaja bukan chatbot (dosen pembimbing memintanya): satu query, satu jawaban,
tanpa riwayat, dan potongan sumber ikut dikembalikan supaya UI bisa menunjukkan asalnya.

Embedding dari sentence-transformers yang jalan lokal (tanpa biaya API), vektor disimpan di Chroma pada disk."""

import os
import re

import chromadb
from openai import OpenAI
from sentence_transformers import SentenceTransformer

from . import usage_store

# multibahasa sengaja: transkrip berbahasa Indonesia dengan istilah Inggris
_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

_model = None
_collection = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=os.getenv("CHROMA_DIR", "chroma_data"))
        # cosine, bukan L2 bawaan Chroma: peringkatnya buruk untuk embedding ini (koleksi L2 menaruh potongan tidak
        # relevan di atas "Keputusan" yang asli). Hanya berlaku saat koleksi dibuat, koleksi yang sudah ada
        # harus dihapus dan dibangun ulang (index ulang rapat yang di-opt in)
        _collection = client.get_or_create_collection("notulis_kb", metadata={"hnsw:space": "cosine"})
    return _collection


_KIND_PREFIX = {
    "executive_summary": "Ringkasan rapat",
    "key_decision": "Keputusan rapat",
}
# kata yang sudah tertanam di embedding setiap potongan lewat _KIND_PREFIX, dikeluarkan juga dari lexical boost
_META_WORDS = {w for label in _KIND_PREFIX.values() for w in re.findall(r"[\w]+", label.lower())}


def _chunks_for(summary: dict) -> list[tuple[str, str]]:
    """Hanya ringkasan eksekutif dan keputusan utama yang diindeks (topik dan action item menambah noise). Ringkasan
    terdiri dari beberapa paragraf dan model hanya membaca ~128 token, jadi satu potongan per paragraf."""
    chunks = []
    for paragraph in (summary.get("executive_summary") or "").split("\n\n"):
        if paragraph.strip():
            chunks.append(("executive_summary", paragraph.strip()))
    for decision in summary.get("key_decisions") or []:
        chunks.append(("key_decision", decision))
    return chunks


def remove_meeting(meeting_id: str) -> None:
    _get_collection().delete(where={"meeting_id": meeting_id})


def index_meeting(meeting_id: str, summary: dict) -> None:
    """(Re-)index satu rapat, untuk rapat yang di-opt in user dan lagi setelah ringkasan ulang. Id potongan
    deterministik, jadi index ulang menimpa, bukan menumpuk duplikat."""
    chunks = _chunks_for(summary)
    # hapus potongan lama dulu, ringkasan ulang bisa menghasilkan lebih sedikit potongan dan upsert tidak menghapus sisanya
    collection = _get_collection()
    collection.delete(where={"meeting_id": meeting_id})
    if not chunks:
        return

    ids = [f"{meeting_id}:{kind}:{i}" for i, (kind, _) in enumerate(chunks)]
    texts = [text for _, text in chunks]
    metadatas = [{"meeting_id": meeting_id, "kind": kind} for kind, _ in chunks]
    # embed dengan label di depan ("Keputusan rapat: ..."), terbukti meningkatkan relevansi: frasa pendek polos
    # kurang konteks untuk model kecil ini. Teks yang disimpan tetap tanpa label, UI menampilkan
    # jenisnya sebagai badge
    to_embed = [f"{_KIND_PREFIX.get(kind, kind)}: {text}" for kind, text in chunks]
    embeddings = _get_model().encode(to_embed).tolist()
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)


# kata fungsi bahasa Indonesia yang umum, supaya lexical boost hanya menyala pada kata isi (nama, istilah)
_STOPWORDS = {
    "yang", "akan", "dengan", "untuk", "dari", "pada", "adalah", "dan", "atau",
    "ini", "itu", "dia", "ia", "saya", "kami", "kita", "kamu", "anda", "mereka",
    "juga", "saat", "karena", "oleh", "para", "tidak", "bisa", "dapat", "sudah",
    "belum", "masih", "agar", "jika", "kalau", "tanpa", "dalam", "atas", "bagi",
    "tentang", "sebagai", "seperti", "lebih", "sangat", "hanya", "saja", "ada",
    "bukan", "semua", "setiap", "antara", "sebelum", "sesudah", "setelah",
    "hingga", "sampai", "mulai", "terus", "lain", "baru", "lama", "banyak",
}


def _lexical_boost(query: str, text: str) -> float:
    """Pencarian hibrida: query kata kunci pendek ("Keputusan kresna") bisa menaruh potongan tanpa "kresna" di atas yang
    ada, karena label jenis mendominasi. Kata isi dari query yang ada di teks potongan itu sendiri
    menaikkannya: 0,15 per kata berbeda, paling banyak 0,3."""
    words = {w for w in re.findall(r"[\w]+", query.lower()) if len(w) >= 4 and w not in _STOPWORDS and w not in _META_WORDS}
    matched = sum(1 for w in words if re.search(rf"\b{re.escape(w)}\b", text.lower()))
    return min(0.3, matched * 0.15)


def search(query: str, meeting_ids: list[str], top_k: int = 5) -> list[dict]:
    """Sampai top_k {meeting_id, kind, text, distance, similarity} dari rapat yang diberikan, terbaik dulu. Pemanggil
    menggabungkan meeting_id dengan tabel meetings, modul ini hanya tahu potongan."""
    collection = _get_collection()
    if not meeting_ids or collection.count() == 0:
        return []
    query_embedding = _get_model().encode([query]).tolist()
    # kumpulan lebih luas dari top_k, lexical boost bisa menaikkan potongan yang tadinya tepat di luar peringkat
    candidate_k = min(top_k * 4, collection.count())
    result = collection.query(
        query_embeddings=query_embedding,
        n_results=candidate_k,
        where={"meeting_id": {"$in": meeting_ids}},
    )

    # jarak cosine adalah 1 - kemiripan (dipotong, noise float bisa melewati 1). Kemiripan mentah dari model ini
    # ada di rentang sempit (~0,1-0,15 tidak relevan, 0,35-0,5 sesuai topik), yang akan terbaca "36%
    # relevan" yang mengecewakan. Jadi yang di bawah _FLOOR dibuang dan _FLOOR.._CEIL diregangkan ke 0-1.
    # ponytail: batasnya dari satu perbandingan manual, ulangi kalau model atau isinya berubah
    _FLOOR, _CEIL = 0.2, 0.6

    matches = []
    for i in range(len(result["ids"][0])):
        distance = result["distances"][0][i]
        text = result["documents"][0][i]
        raw = max(0.0, 1.0 - distance)
        blended = min(1.0, raw + _lexical_boost(query, text))
        if blended < _FLOOR:
            continue
        similarity = min(1.0, (blended - _FLOOR) / (_CEIL - _FLOOR))
        matches.append(
            {
                "meeting_id": result["metadatas"][0][i]["meeting_id"],
                "kind": result["metadatas"][0][i]["kind"],
                "text": text,
                "distance": distance,
                "similarity": similarity,
            }
        )
    matches.sort(key=lambda m: m["similarity"], reverse=True)
    return matches[:top_k]


_ANSWER_SYSTEM_PROMPT = (
    "You answer a question about a team's past meetings using ONLY the excerpts "
    "given below, each tagged with which meeting it's from. Do not use any "
    "outside knowledge and do not invent meetings, people, dates, or facts not "
    "present in the excerpts. Write a short, direct answer (2-4 sentences), in "
    "the same language as the question, naturally mentioning which meeting(s) "
    "it's based on. If the excerpts genuinely don't answer the question, say so "
    "plainly instead of guessing - do not pad with a vague answer."
)


def answer(query: str, results: list[dict]) -> str | None:
    """Satu jawaban singkat dari hasil yang sudah diambil (masing-masing dengan meeting_title dan text). None kalau tidak ada
    bahan jawaban atau panggilannya gagal, potongan mentahnya tetap berguna. Sekali jalan, tanpa riwayat."""
    if not results:
        return None
    context = "\n".join(f"[{r['meeting_title']}] {r['text']}" for r in results)
    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _ANSWER_SYSTEM_PROMPT},
                {"role": "user", "content": f"Excerpts:\n{context}\n\nQuestion: {query}"},
            ],
        )
        try:
            # tidak terikat satu rapat, hasilnya mencakup beberapa
            usage_store.log_usage(None, "kb_answer", "gpt-4o-mini", response.usage)
        except Exception as e:
            print(f"[usage_store] failed to log kb_answer usage: {e}")
        return response.choices[0].message.content
    except Exception as e:
        print(f"[knowledge_base] failed to synthesize answer: {e}")
        return None
