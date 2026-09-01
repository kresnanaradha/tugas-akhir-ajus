import { PlaceholderPage } from "@/components/PlaceholderPage";

export default function LaporanScreen() {
  return (
    <PlaceholderPage
      icon="bar-chart-2"
      title="Laporan"
      description="Analisis aktivitas rapat dan penggunaan sistem oleh organisasi."
      comingFeatures={[
        "Organization Summary: total rapat, durasi rapat, topik pembahasan",
        "User Activity: jumlah rekaman dan jam transkripsi per pengguna",
        "Recording Summary: total rekaman, durasi total, status rekaman, platform yang dipakai",
        "Ekspor laporan dalam format PDF",
      ]}
    />
  );
}
