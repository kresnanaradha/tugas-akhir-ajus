import { PlaceholderPage } from "@/components/PlaceholderPage";

export default function RapatScreen() {
  return (
    <PlaceholderPage
      icon="mic"
      title="Rapat"
      description="Daftar rapat yang direkam bot, transkrip otomatis, dan ringkasan AI-nya."
      comingFeatures={[
        "Bot bergabung otomatis ke Google Meet / Zoom, progres real-time (Launching, Joining, Recording, Uploading)",
        "Transkripsi otomatis dengan timestamp per kata dan label pembicara (speaker label)",
        "Fitur edit transcript untuk memperbaiki kesalahan transkripsi",
        "Unduh transkrip dalam format TXT, DOCX, dan PDF",
        "Ringkasan AI: executive summary, key decisions, topics discussed",
      ]}
    />
  );
}
