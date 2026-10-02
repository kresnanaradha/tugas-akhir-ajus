import { Feather } from "@expo/vector-icons";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { StatCard } from "@/components/StatCard";
import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import {
  createTeam,
  getBillingStatus,
  getMyTeam,
  inviteToTeam,
  leaveTeam,
  removeTeamMember,
  renameTeam,
  updateTeamMemberRole,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { initialsOf } from "@/lib/format";

// Deliberately NOT built here: nested sub-teams and a hard per-team seat
// quota (Team is a flat monthly fee, not metered per seat — see CLAUDE.md's
// "Team" section). Per-meeting sharing lives on rapat/[id].jsx instead.

const BENEFITS = [
  { icon: "share-2", title: "Bagikan hasil rapat", body: "Pilih rapat mana yang terlihat oleh anggota team, per rapat, bukan otomatis semuanya." },
  { icon: "user-plus", title: "Undang lewat tautan atau email", body: "Anggota baru cukup membuka tautan undangan, berlaku 7 hari." },
  { icon: "shield", title: "Peran Admin & Member", body: "Admin mengelola anggota dan undangan, Member melihat rapat yang dibagikan." },
];

function PageHeader({ title, count, description }) {
  return (
    <View style={styles.headerRow}>
      <View style={{ flex: 1 }}>
        <View style={styles.titleRow}>
          <Text style={styles.title}>{title}</Text>
          {count != null && (
            <View style={styles.countBadge}>
              <Text style={styles.countBadgeLabel}>{count}</Text>
            </View>
          )}
        </View>
        <Text style={styles.description}>{description}</Text>
      </View>
    </View>
  );
}

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

function CreateTeamPanel({ onCreated }) {
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

function UpsellPanel() {
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
        <Pressable style={styles.primaryButton} onPress={() => router.push("/pengaturan")}>
          <Text style={styles.primaryButtonLabel}>Lihat Paket Team</Text>
        </Pressable>
      </View>
      <View style={styles.sideCol}>
        <BenefitList />
      </View>
    </View>
  );
}

function InvitePanel() {
  const [email, setEmail] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [invite, setInvite] = useState(null);
  const [copied, setCopied] = useState(false);

  async function handleInvite() {
    setSending(true);
    setError("");
    setInvite(null);
    try {
      setInvite(await inviteToTeam(email.trim() || null));
      setEmail("");
    } catch (e) {
      setError(e.message || "Gagal membuat undangan");
    } finally {
      setSending(false);
    }
  }

  function handleCopy() {
    navigator.clipboard?.writeText(invite.invite_url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <View style={styles.sidePanel}>
      <Text style={styles.panelTitle}>Undang Anggota</Text>
      <Text style={styles.hint}>Isi email untuk kirim undangan, atau kosongkan untuk dapat tautan saja.</Text>
      <TextInput
        style={styles.input}
        placeholder="Email (opsional)"
        placeholderTextColor={colors.inkFaint}
        autoCapitalize="none"
        keyboardType="email-address"
        value={email}
        onChangeText={setEmail}
      />
      <Pressable style={[styles.primaryButton, sending && styles.buttonDisabled]} disabled={sending} onPress={handleInvite}>
        {sending ? <ActivityIndicator size="small" color={colors.ink} /> : <Text style={styles.primaryButtonLabel}>Buat Undangan</Text>}
      </Pressable>
      {!!error && <Text style={styles.errorText}>{error}</Text>}
      {!!invite && (
        <View style={styles.inviteLinkBox}>
          <Text style={styles.inviteLinkText} numberOfLines={2}>
            {invite.invite_url}
          </Text>
          <Pressable style={styles.smallButton} onPress={handleCopy}>
            <Feather name={copied ? "check" : "copy"} size={12} color={colors.ink} />
            <Text style={styles.smallButtonLabel}>{copied ? "Tersalin" : "Salin Tautan"}</Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

function TeamNameRow({ team, isAdmin, onRenamed }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(team.name);
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!name.trim() || name.trim() === team.name) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      onRenamed(await renameTeam(team.id, name.trim()));
    } finally {
      setSaving(false);
      setEditing(false);
    }
  }

  if (editing) {
    return (
      <View style={styles.inlineForm}>
        <TextInput style={styles.input} value={name} onChangeText={setName} autoFocus onSubmitEditing={handleSave} />
        <Pressable style={styles.smallButton} onPress={handleSave} disabled={saving}>
          <Text style={styles.smallButtonLabel}>{saving ? "..." : "Simpan"}</Text>
        </Pressable>
        <Pressable style={styles.smallButton} onPress={() => setEditing(false)} disabled={saving}>
          <Text style={styles.smallButtonLabel}>Batal</Text>
        </Pressable>
      </View>
    );
  }
  return (
    <View style={styles.teamNameRow}>
      <Text style={styles.teamName}>{team.name}</Text>
      {isAdmin && (
        <Pressable onPress={() => setEditing(true)} hitSlop={8}>
          <Feather name="edit-2" size={14} color={colors.inkFaint} />
        </Pressable>
      )}
    </View>
  );
}

function MemberRow({ member, isAdmin, isSelf, onRemove, onRoleChange }) {
  const memberIsAdmin = member.team_role === "admin";
  return (
    <View style={styles.memberRow}>
      <View style={styles.avatar}>
        <Text style={styles.avatarLabel}>{initialsOf(member.name)}</Text>
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.memberName} numberOfLines={1}>
          {member.name}
          {isSelf && " (Anda)"}
        </Text>
        <Text style={styles.memberEmail} numberOfLines={1}>
          {member.email}
        </Text>
      </View>
      <View style={[styles.roleBadge, memberIsAdmin && styles.roleBadgeAdmin]}>
        <Text style={[styles.roleBadgeLabel, memberIsAdmin && styles.roleBadgeLabelAdmin]}>{memberIsAdmin ? "Admin" : "Member"}</Text>
      </View>
      {isAdmin && !isSelf && (
        <View style={styles.memberActions}>
          <Pressable style={styles.smallButton} onPress={() => onRoleChange(member.id, memberIsAdmin ? "member" : "admin")}>
            <Text style={styles.smallButtonLabel}>{memberIsAdmin ? "Jadikan Member" : "Jadikan Admin"}</Text>
          </Pressable>
          <Pressable style={styles.iconButton} onPress={() => onRemove(member.id)} hitSlop={8}>
            <Feather name="user-x" size={14} color={colors.danger} />
          </Pressable>
        </View>
      )}
    </View>
  );
}

function TeamView({ team, members, isAdmin, myId, onRefresh }) {
  const [confirmLeaveOpen, setConfirmLeaveOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [leaveError, setLeaveError] = useState("");
  const adminCount = members.filter((m) => m.team_role === "admin").length;

  async function handleLeave() {
    setLeaving(true);
    setLeaveError("");
    try {
      await leaveTeam();
      onRefresh();
    } catch (e) {
      setLeaveError(e.message || "Gagal keluar dari team");
      setLeaving(false);
    }
  }

  return (
    <>
      <View style={styles.statGrid}>
        <StatCard value={String(members.length)} label="Total Anggota" />
        <StatCard value={String(adminCount)} label="Admin" />
        <StatCard value={String(members.length - adminCount)} label="Member" />
        <StatCard value={isAdmin ? "Admin" : "Member"} label="Peran Anda" deltaColor={colors.goldDeep} />
      </View>

      <View style={styles.mainGrid}>
        <View style={[styles.panel, styles.mainCol]}>
          <View style={styles.panelHeader}>
            <TeamNameRow team={team} isAdmin={isAdmin} onRenamed={onRefresh} />
            <Text style={styles.panelMeta}>{members.length} anggota</Text>
          </View>
          {members.map((m) => (
            <MemberRow
              key={m.id}
              member={m}
              isAdmin={isAdmin}
              isSelf={m.id === myId}
              onRemove={(id) => removeTeamMember(id).then(onRefresh)}
              onRoleChange={(id, role) => updateTeamMemberRole(id, role).then(onRefresh)}
            />
          ))}
        </View>

        <View style={styles.sideCol}>
          {isAdmin && <InvitePanel />}
          <View style={styles.sidePanel}>
            <Text style={styles.panelTitle}>Berbagi Rapat</Text>
            <Text style={styles.hint}>
              Rapat tidak otomatis terlihat oleh team. Buka detail rapat Anda lalu klik "Bagikan ke Team" untuk
              membagikannya.
            </Text>
          </View>
          <View style={styles.sidePanel}>
            <Text style={styles.panelTitle}>Keluar dari Team</Text>
            <Text style={styles.hint}>Rapat Anda sendiri tetap aman, hanya akses ke rapat teammate yang hilang.</Text>
            {!!leaveError && <Text style={styles.errorText}>{leaveError}</Text>}
            <Pressable style={styles.dangerButton} onPress={() => setConfirmLeaveOpen(true)}>
              <Feather name="log-out" size={13} color={colors.danger} />
              <Text style={styles.dangerButtonLabel}>Keluar dari Team</Text>
            </Pressable>
          </View>
        </View>
      </View>

      <Modal visible={confirmLeaveOpen} transparent animationType="fade" onRequestClose={() => setConfirmLeaveOpen(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <View style={styles.modalIconWrap}>
              <Feather name="alert-triangle" size={20} color={colors.danger} />
            </View>
            <Text style={styles.modalTitle}>Keluar dari team?</Text>
            <Text style={styles.modalBody}>
              Anda tidak akan lagi melihat rapat yang dibagikan teammate. Rapat Anda sendiri tetap aman.
            </Text>
            <View style={styles.modalActions}>
              <Pressable style={styles.modalCancelButton} onPress={() => setConfirmLeaveOpen(false)} disabled={leaving}>
                <Text style={styles.modalCancelLabel}>Batal</Text>
              </Pressable>
              <Pressable style={styles.modalConfirmButton} onPress={handleLeave} disabled={leaving}>
                {leaving ? <ActivityIndicator size="small" color={colors.white} /> : <Text style={styles.modalConfirmLabel}>Ya, Keluar</Text>}
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </>
  );
}

export default function TeamScreen() {
  const { user, updateUser } = useAuth();
  const [status, setStatus] = useState("loading"); // loading | error | done
  const [teamData, setTeamData] = useState(null); // {team, members} | null
  const [plan, setPlan] = useState("free");
  const [error, setError] = useState("");

  function load() {
    Promise.all([getMyTeam(), getBillingStatus()])
      .then(([team, billing]) => {
        setTeamData(team);
        setPlan(billing.status === "active" ? billing.plan : "free");
        setStatus("done");
      })
      .catch((e) => {
        setError(e.message || "Gagal memuat data team");
        setStatus("error");
      });
  }

  useEffect(load, []);

  function handleCreated(team) {
    setTeamData({ team, members: [{ ...user, team_role: "admin" }] });
    updateUser({ ...user, team_id: team.id, team_role: "admin" });
  }

  const isAdmin = teamData?.members.find((m) => m.id === user?.id)?.team_role === "admin";

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <PageHeader
          title="Team"
          count={status === "done" && teamData ? teamData.members.length : null}
          description="Kelola anggota team dan bagikan hasil rapat."
        />

        {status === "loading" && (
          <View style={styles.stateBox}>
            <ActivityIndicator color={colors.gold} />
          </View>
        )}
        {status === "error" && <Text style={styles.errorText}>{error}</Text>}

        {status === "done" && !teamData && plan === "team" && <CreateTeamPanel onCreated={handleCreated} />}
        {status === "done" && !teamData && plan !== "team" && <UpsellPanel />}
        {status === "done" && teamData && (
          <TeamView team={teamData.team} members={teamData.members} isAdmin={isAdmin} myId={user?.id} onRefresh={load} />
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { alignItems: "center", padding: spacing.lg },
  content: { gap: spacing.md, maxWidth: 1200, width: "100%" },

  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: spacing.lg },
  titleRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  title: { ...type.h1, fontSize: 24, color: colors.ink },
  countBadge: { backgroundColor: colors.goldSoft, borderRadius: radius.pill, paddingVertical: 3, paddingHorizontal: 10 },
  countBadgeLabel: { ...type.small, fontWeight: "700", color: colors.goldDeep },
  description: { ...type.body, color: colors.inkSoft, marginTop: 2 },
  stateBox: { alignItems: "center", padding: spacing.xl },
  errorText: { ...type.small, color: colors.danger },
  hint: { ...type.small, color: colors.inkFaint, lineHeight: 17 },

  statGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  mainGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, alignItems: "flex-start" },
  mainCol: { flex: 2.4, minWidth: 420 },
  sideCol: { flex: 1, minWidth: 300, gap: spacing.md },

  panel: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: "hidden",
    ...shadow.card,
  },
  panelHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  panelMeta: { ...type.small, color: colors.inkFaint },
  sidePanel: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: spacing.sm,
    ...shadow.card,
  },
  panelTitle: { ...type.h2, color: colors.ink },

  teamNameRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  teamName: { ...type.h2, color: colors.ink },

  memberRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: 10,
    paddingHorizontal: spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  avatar: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.ink, alignItems: "center", justifyContent: "center" },
  avatarLabel: { color: colors.white, fontWeight: "700", fontSize: 13 },
  memberName: { ...type.bodyMedium, fontWeight: "600", color: colors.ink },
  memberEmail: { ...type.small, color: colors.inkFaint },
  memberActions: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  roleBadge: { backgroundColor: colors.surfaceSunken, borderRadius: radius.pill, paddingVertical: 3, paddingHorizontal: 10 },
  roleBadgeAdmin: { backgroundColor: colors.goldSoft },
  roleBadgeLabel: { ...type.small, fontWeight: "700", color: colors.inkFaint },
  roleBadgeLabelAdmin: { color: colors.goldDeep },
  iconButton: { padding: 6, borderRadius: radius.sm, backgroundColor: colors.dangerSoft },

  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    backgroundColor: colors.surfaceSunken,
    paddingHorizontal: spacing.md,
    paddingVertical: 9,
    ...type.body,
    color: colors.ink,
    outlineStyle: "none",
  },
  inlineForm: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flex: 1 },
  primaryButton: {
    backgroundColor: colors.gold,
    borderRadius: radius.sm,
    paddingVertical: 10,
    paddingHorizontal: spacing.lg,
    alignItems: "center",
    justifyContent: "center",
    ...shadow.card,
  },
  buttonDisabled: { opacity: 0.5 },
  primaryButtonLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },
  smallButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    paddingVertical: 6,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
  },
  smallButtonLabel: { ...type.small, fontWeight: "600", color: colors.ink },
  dangerButton: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    borderWidth: 1,
    borderColor: colors.danger,
    borderRadius: radius.sm,
    paddingVertical: 9,
    marginTop: spacing.xs,
  },
  dangerButtonLabel: { ...type.small, fontWeight: "700", color: colors.danger },

  inviteLinkBox: { gap: spacing.sm, backgroundColor: colors.surfaceSunken, borderRadius: radius.sm, padding: spacing.md },
  inviteLinkText: { ...type.small, color: colors.inkSoft },

  emptyPanel: { alignItems: "center", gap: spacing.sm, paddingVertical: spacing.xxl, paddingHorizontal: spacing.xl },
  emptyIcon: {
    width: 56,
    height: 56,
    borderRadius: radius.md,
    backgroundColor: colors.goldSoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xs,
  },
  emptyTitle: { ...type.h1, fontSize: 20, color: colors.ink, textAlign: "center" },
  emptyBody: { ...type.body, color: colors.inkFaint, textAlign: "center", lineHeight: 20, maxWidth: 440 },
  createForm: { flexDirection: "row", gap: spacing.sm, alignSelf: "stretch", maxWidth: 480, marginTop: spacing.sm },

  benefitRow: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start" },
  benefitIcon: {
    width: 32,
    height: 32,
    borderRadius: radius.sm,
    backgroundColor: colors.goldSoft,
    alignItems: "center",
    justifyContent: "center",
  },
  benefitTitle: { ...type.bodyMedium, fontWeight: "600", color: colors.ink },
  benefitBody: { ...type.small, color: colors.inkFaint, lineHeight: 17, marginTop: 1 },

  modalOverlay: { flex: 1, backgroundColor: "rgba(27,31,43,0.45)", alignItems: "center", justifyContent: "center", padding: spacing.lg },
  modalCard: { maxWidth: 360, width: "100%", backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.lg, alignItems: "center", gap: spacing.sm },
  modalIconWrap: { width: 44, height: 44, borderRadius: radius.sm, backgroundColor: colors.dangerSoft, alignItems: "center", justifyContent: "center", marginBottom: spacing.xs },
  modalTitle: { ...type.h2, color: colors.ink, textAlign: "center" },
  modalBody: { ...type.body, color: colors.inkSoft, textAlign: "center", lineHeight: 19 },
  modalActions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, alignSelf: "stretch" },
  modalCancelButton: { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingVertical: 11, alignItems: "center" },
  modalCancelLabel: { ...type.bodyMedium, fontWeight: "600", color: colors.ink },
  modalConfirmButton: { flex: 1, backgroundColor: colors.danger, borderRadius: radius.sm, paddingVertical: 11, alignItems: "center" },
  modalConfirmLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.white },
});
