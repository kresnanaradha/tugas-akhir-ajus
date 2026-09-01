import { PlaceholderPage } from "@/components/PlaceholderPage";

export default function OrganisasiScreen() {
  return (
    <PlaceholderPage
      icon="layers"
      title="Organisasi"
      description="Kelola anggota, hak akses, dan paket langganan organisasi."
      comingFeatures={[
        "Manajemen pengguna dengan dua peran: Admin dan Member (multi-tenant, data antar organisasi terpisah)",
        "Admin membuat sesi rapat dan menginput tautan rapat",
        "Kelola paket langganan: Free, Pro, Enterprise — pembayaran via Xendit",
        "Riwayat pembayaran, unduhan invoice, auto-downgrade saat kuota habis",
      ]}
    />
  );
}
