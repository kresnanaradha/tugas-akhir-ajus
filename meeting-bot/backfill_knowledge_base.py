"""One-off backfill: indexes every existing meeting's summary into the RAG
Knowledge Base (pipeline/knowledge_base.py) — needed once, since indexing
only happens automatically going forward (summarize() calls it on every new
summary). Safe to re-run: index_meeting() deletes a meeting's old chunks
before adding new ones.

Run once from meeting-bot/: python backfill_knowledge_base.py
"""

from dotenv import load_dotenv

load_dotenv()

from pipeline import artifacts, knowledge_base, meetings_store  # noqa: E402


def main():
    indexed = 0
    skipped = 0
    for m in meetings_store.list_meetings():
        summary = artifacts.load_summary(m["id"])
        if not summary:
            skipped += 1
            continue
        knowledge_base.index_meeting(m["id"], summary)
        indexed += 1
        print(f"indexed {m['id']} ({m['title']})")

    print(f"\nDone. indexed={indexed} skipped(no summary)={skipped}")


if __name__ == "__main__":
    main()
