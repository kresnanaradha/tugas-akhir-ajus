import { PlaceholderPage } from "@/components/PlaceholderPage";

export default function KnowledgeBaseScreen() {
  return (
    <PlaceholderPage
      icon="search"
      title="Knowledge Base"
      description="Cari dan tanya jawab lintas seluruh hasil rapat organisasi secara semantik."
      comingFeatures={[
        "Ringkasan rapat disimpan otomatis ke Knowledge Base",
        "Diproses dengan LangChain, Hugging Face untuk embeddings, dan Chroma sebagai vector database",
        "Pencarian semantik pakai bahasa alami, bukan sekadar kata kunci",
        "Tanya jawab terhadap hasil rapat sebelumnya, jawaban dari GPT-4o mini beserta sumber rapatnya",
      ]}
    />
  );
}
