// tampilan untuk user yang belum punya team: buat team (paket Team) atau ajakan upgrade, plus daftar manfaatnya
import { Feather } from "@expo/vector-icons";
import { router } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Pressable, Text, TextInput, View } from "react-native";
import { styles } from "@/components/team/styles";
import { colors, spacing } from "@/constants/theme";
import { createTeam } from "@/lib/api";

const BENEFITS = [
  { icon: "share-2", title: "Bagikan hasil rapat", body: "Pilih rapat mana yang terlihat oleh anggota team, per rapat, bukan otomatis semuanya." },
  { icon: "user-plus", title: "Undang lewat tautan atau email", body: "Anggota baru cukup membuka tautan undangan, berlaku 7 hari." },
  { icon: "shield", title: "Peran Admin & Member", body: "Admin mengelola anggota dan undangan, Member melihat rapat yang dibagikan." },
];

function BenefitList() {
  return (
    <View style={styles.sidePanel}>
      <Text style={styles.panelTitle}>Yang Anda Dapatkan</Text>
      <View style={{ gap: spacing.md }}>
        {BENEFITS.map((b) => (
          <View key={b.title} style={styles.benefitRow}>
            <View style={styles.benefitIcon}>
              <Feather name={b.icon} size={15} color={colors.goldDeep} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.benefitTitle}>{b.title}</Text>
              <Text style={styles.benefitBody}>{b.body}</Text>
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

export function CreateTeamPanel({ onCreated }) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleCreate() {
    if (!name.trim()) return;
    setSaving(true);
    setError("");
    try {
      onCreated(await createTeam(name.trim()));
    } catch (e) {
      setError(e.message || "Gagal membuat team");
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={styles.mainGrid}>
      <View style={[styles.panel, styles.mainCol, styles.emptyPanel]}>
        <View style={styles.emptyIcon}>
          <Feather name="users" size={24} color={colors.goldDeep} />
        </View>
        <Text style={styles.emptyTitle}>Buat Team Pertama Anda</Text>
        <Text style={styles.emptyBody}>
          Beri nama team, lalu undang rekan kerja. Anda otomatis jadi admin pertama.
        </Text>
        <View style={styles.createForm}>
          <TextInput
            style={styles.input}
            placeholder="Nama team, mis. Tim Produk"
            placeholderTextColor={colors.inkFaint}
            value={name}
            onChangeText={setName}
            onSubmitEditing={handleCreate}
          />
          <Pressable style={[styles.primaryButton, !name.trim() && styles.buttonDisabled]} disabled={!name.trim() || saving} onPress={handleCreate}>
            {saving ? <ActivityIndicator size="small" color={colors.ink} /> : <Text style={styles.primaryButtonLabel}>Buat Team</Text>}
          </Pressable>
        </View>
        {!!error && <Text style={styles.errorText}>{error}</Text>}
      </View>
      <View style={styles.sideCol}>
        <BenefitList />
      </View>
    </View>
  );
}

export function UpsellPanel() {
  return (
    <View style={styles.mainGrid}>
      <View style={[styles.panel, styles.mainCol, styles.emptyPanel]}>
        <View style={styles.emptyIcon}>
          <Feather name="users" size={24} color={colors.goldDeep} />
        </View>
        <Text style={styles.emptyTitle}>Anda Belum Memiliki Team</Text>
        <Text style={styles.emptyBody}>
          Notulis tetap bisa dipakai sendirian. Membuat team memerlukan paket Team, supaya hasil rapat bisa dibagikan
          dan anggota dikelola bersama.
        </Text>
        <Pressable style={styles.primaryButton} onPress={() => router.push("/billing")}>
          <Text style={styles.primaryButtonLabel}>Lihat Paket Team</Text>
        </Pressable>
      </View>
      <View style={styles.sideCol}>
        <BenefitList />
      </View>
    </View>
  );
}
