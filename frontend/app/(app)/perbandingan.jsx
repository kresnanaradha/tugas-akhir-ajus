import { PlaceholderPage } from "@/components/PlaceholderPage";

export default function PerbandinganScreen() {
  return (
    <PlaceholderPage
      icon="shuffle"
      title="Perbandingan Rapat"
      description="Bandingkan dua hasil rapat secara berdampingan."
      comingFeatures={[
        "Pilih dua rapat untuk dibandingkan side-by-side",
        "Menyoroti perbedaan ringkasan dan topik pembahasan antar rapat",
        "Ekspor hasil perbandingan dalam format PDF",
      ]}
    />
  );
}
