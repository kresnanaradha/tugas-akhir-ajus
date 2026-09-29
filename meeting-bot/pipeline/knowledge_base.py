"""RAG knowledge base over meeting summaries — a query embeds to a vector,
Chroma finds the closest-matching summary chunks, and GPT-4o mini writes one
short answer grounded only in those chunks. Deliberately NOT a chatbot per
the advisor's explicit direction: single query -> single answer, no
conversation history, no follow-up turns — every call is independent, and
the raw source chunks always go back to the caller alongside the answer so
the UI can show exactly where it came from (see app.py's
/knowledge-base/search).

Stack matches the original thesis proposal: sentence-transformers
(HuggingFace) for embeddings, run locally (no API cost, consistent with
transcribe.py already running everything else locally), and Chroma as the
vector database, persisted to disk like `recordings/` — no separate DB
server to run.
"""

import os
import re

import chromadb
from openai import OpenAI
from sentence_transformers import SentenceTransformer

from . import usage_store

# Multilingual, not the more common English-only MiniLM — this app's
# transcripts are Indonesian with mixed-in English technical terms (see
# CLAUDE.md's "Transcription/summarization notes"), so the embedding model
# needs to actually understand Indonesian semantics, not just tokenize it.
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
        # Chroma defaults to L2 (Euclidean) distance, which ranks sentence-
        # transformers embeddings poorly — these models are trained/evaluated
        # for cosine similarity, so L2 on them produces noticeably worse
        # relevance ordering (confirmed live: an L2 collection ranked
        # unrelated "Topik" chunks above the actual "Keputusan" chunks for a
        # query literally asking "apa keputusan..."). hnsw:space only takes
        # effect at collection creation — an already-created L2 collection
        # can't be switched in place, it has to be deleted and rebuilt (see
        # backfill_knowledge_base.py).
        _collection = client.get_or_create_collection("notulis_kb", metadata={"hnsw:space": "cosine"})
    return _collection


_KIND_PREFIX = {
    "executive_summary": "Ringkasan rapat",
    "key_decision": "Keputusan rapat",
}
# Words baked into every chunk's embedding via _KIND_PREFIX ("rapat" is in
# both labels) -- excluded from the lexical boost below too, or a query like
# "apa keputusan rapat" would boost whichever chunk happens to literally
# repeat "rapat" in its own sentence, recreating the same bias on a chunk's
# own text instead of the injected label.
_META_WORDS = {w for label in _KIND_PREFIX.values() for w in re.findall(r"[\w]+", label.lower())}


def _chunks_for(summary: dict) -> list[tuple[str, str]]:
    """Only the executive summary and key decisions go into the KB (advisor's
    call: topics/action items add noise, the summary already covers them).
    The summary is now several paragraphs long, and this embedding model only
    reads ~128 tokens per input, so it's embedded one paragraph per chunk
    instead of as one blob whose tail would be silently ignored."""
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
    """(Re-)indexes one meeting's summary — only for meetings the user opted
    in (POST /meetings/<id>/knowledge-base), and again after a re-summarize
    from the transcript editor if it's still opted in. Chunk ids are deterministic (meeting_id + kind + position), so
    re-indexing the same meeting overwrites its old chunks via upsert
    instead of accumulating duplicates every time a transcript gets edited
    and re-summarized."""
    chunks = _chunks_for(summary)
    # Clear this meeting's old chunks first — a re-summarize can end up with
    # fewer chunks than before (e.g. an action item got removed), and upsert
    # alone wouldn't delete the now-stale extra ones.
    collection = _get_collection()
    collection.delete(where={"meeting_id": meeting_id})
    if not chunks:
        return

    ids = [f"{meeting_id}:{kind}:{i}" for i, (kind, _) in enumerate(chunks)]
    texts = [text for _, text in chunks]
    metadatas = [{"meeting_id": meeting_id, "kind": kind} for kind, _ in chunks]
    # Embed a version prefixed with a natural-language label of its kind
    # ("Keputusan rapat: ...") rather than the bare text — confirmed via a
    # direct embedding comparison that this measurably improves relevance:
    # without it, a query literally asking "apa keputusan..." ranked an
    # unrelated "Topik" chunk above the actual decision text, because these
    # short bare phrases don't carry enough context on their own for this
    # (small, multilingual) embedding model. The *stored* document stays the
    # original unprefixed text — the frontend already shows the kind as a
    # separate colored badge, so repeating it in the text would be redundant.
    to_embed = [f"{_KIND_PREFIX.get(kind, kind)}: {text}" for kind, text in chunks]
    embeddings = _get_model().encode(to_embed).tolist()
    collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)


# Common Indonesian function words -- excluded from the lexical boost below
# so it only fires on content words (names, specific terms), not on "akan"/
# "dengan"/etc, which would otherwise match almost every sentence and
# recreate the exact bias this is meant to fix.
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
    """Dense embeddings compress specific names/terms into similar regions as
    other content, so a short keyword-style query (e.g. "Keputusan kresna")
    can rank a chunk that doesn't even mention "kresna" above one that does
    -- confirmed empirically: the _KIND_PREFIX label below dominates a
    2-word query that happens to share a word with it. This is the standard
    fix (hybrid dense+lexical search): a real content word from the query
    that appears verbatim in the chunk's own text (not the injected kind
    label) nudges it up. 0.15 per distinct matched word, capped at 0.3.
    """
    words = {w for w in re.findall(r"[\w]+", query.lower()) if len(w) >= 4 and w not in _STOPWORDS and w not in _META_WORDS}
    boundary = chr(92) + "b"
    matched = sum(1 for w in words if re.search(boundary + re.escape(w) + boundary, text.lower()))
    return min(0.3, matched * 0.15)


def search(query: str, meeting_ids: list[str], top_k: int = 5) -> list[dict]:
    """Returns up to top_k {meeting_id, kind, text, distance} matches from the
    given meetings only, closest first. Caller (app.py) joins meeting_id against the meetings
    table for title/date/platform — this module only knows about chunks."""
    collection = _get_collection()
    if not meeting_ids or collection.count() == 0:
        return []
    query_embedding = _get_model().encode([query]).tolist()
    # Widen the candidate pool beyond top_k -- the lexical boost below can
    # promote a chunk that ranked just outside a bare-cosine top_k.
    candidate_k = min(top_k * 4, collection.count())
    result = collection.query(
        query_embeddings=query_embedding,
        n_results=candidate_k,
        where={"meeting_id": {"$in": meeting_ids}},
    )

    # Cosine distance is 1 - cosine_similarity, so this recovers a plain
    # 0-1 similarity score (clamped — a distance slightly over 1 from
    # floating-point noise would otherwise go negative).
    #
    # Raw cosine similarity from this (multilingual MiniLM) model doesn't
    # spread across 0-1 the way "percent relevant" implies: empirically, a
    # genuinely on-topic match sits around 0.35-0.5, and a totally unrelated
    # one around 0.1-0.15 -- confirmed by comparing "apa keputusan rapat"
    # (0.49) against "resep nasi goreng" (0.15) on the same collection. Shown
    # raw, a correct top match reads as a discouraging "36% relevan". _FLOOR
    # drops noise below the "unrelated" range instead of always forcing
    # top_k results regardless of quality; _CEIL..._FLOOR is rescaled to 0-1
    # so a genuinely strong match reads like one.
    # ponytail: bounds picked from one manual comparison, not a proper
    # calibration set -- revisit if this model or the KB's content changes.
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
    "plainly instead of guessing — do not pad with a vague answer."
)


def answer(query: str, results: list[dict]) -> str | None:
    """Synthesizes one short answer from already-retrieved, already-enriched
    search results (each with meeting_title + text — see app.py's
    /knowledge-base/search, which builds these from search() above). Returns
    None if there's nothing to ground an answer in, or the OpenAI call fails
    (best-effort: the raw source chunks are still useful on their own, so a
    synthesis failure shouldn't break the whole search response). One-shot,
    stateless — no conversation history is kept or sent, by design (see
    module docstring)."""
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
            # meeting_id=None — this call spans whichever meetings matched,
            # not one specific meeting, unlike summarize.py's usage logging.
            usage_store.log_usage(None, "kb_answer", "gpt-4o-mini", response.usage)
        except Exception as e:
            print(f"[usage_store] failed to log kb_answer usage: {e}")
        return response.choices[0].message.content
    except Exception as e:
        print(f"[knowledge_base] failed to synthesize answer: {e}")
        return None
