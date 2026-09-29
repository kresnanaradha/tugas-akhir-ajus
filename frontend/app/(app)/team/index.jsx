import { Feather } from "@expo/vector-icons";
import { router } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

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

// Deliberately NOT built here (see CLAUDE.md's "Known POC gaps" once noted
// there): sub-teams/nested hierarchies, and a hard per-team seat quota — the
// Team plan is a flat monthly fee (billing_store.PLAN_PRICES), not metered
// per seat, so capping member count would enforce a limit the billing itself
// doesn't charge for. Everything else asked for (per-meeting share toggle —
// see rapat/[id].jsx's "Bagikan ke Team" — invite via link + email, Admin/
// Member roles) is built.

function CreateTeamCard({ onCreated }) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleCreate() {
    if (!name.trim()) return;
    setSaving(true);
    setError("");
    try {
      const team = await createTeam(name.trim());
      onCreated(team);
    } catch (e) {
      setError(e.message || "Gagal membuat team");
    } finally {
      setSaving(false);
    }
  }

  return (
    <View style={styles.card}>
      <View style={styles.iconWrap}>
        <Feather name="users" size={20} color={colors.goldDeep} />
      </View>
      <Text style={styles.cardTitle}>Buat Team</Text>
      <Text style={styles.cardBody}>
        Beri nama team Anda, lalu undang anggota lewat tautan atau email. Anda jadi admin pertama.
      </Text>
      <View style={styles.inlineForm}>
        <TextInput
          style={styles.input}
          placeholder="Nama team"
          placeholderTextColor={colors.inkFaint}
          value={name}
          onChangeText={setName}
        />
        <Pressable style={[styles.primaryButton, !name.trim() && styles.buttonDisabled]} disabled={!name.trim() || saving} onPress={handleCreate}>
          {saving ? <ActivityIndicator size="small" color={colors.ink} /> : <Text style={styles.primaryButtonLabel}>Buat Team</Text>}
        </Pressable>
      </View>
      {!!error && <Text style={styles.errorText}>{error}</Text>}
    </View>
  );
}

function UpsellCard() {
  return (
    <View style={styles.card}>
      <View style={styles.iconWrap}>
        <Feather name="users" size={20} color={colors.goldDeep} />
      </View>
      <Text style={styles.cardTitle}>Anda Belum Memiliki Team</Text>
      <Text style={styles.cardBody}>
        Notulis tetap bisa dipakai sendirian — rapat, transkrip, dan ringkasan tersimpan di akun Anda. Membuat team
        perlu paket Team, supaya bisa berbagi hasil rapat dan kelola anggota bareng orang lain.
      </Text>
      <Pressable style={styles.primaryButton} onPress={() => router.push("/pengaturan")}>
        <Text style={styles.primaryButtonLabel}>Lihat Paket Team</Text>
      </Pressable>
    </View>
  );
}

function InviteBox() {
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
      const result = await inviteToTeam(email.trim() || null);
      setInvite(result);
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
    <View style={styles.inviteBox}>
      <Text style={styles.fieldLabel}>UNDANG ANGGOTA</Text>
      <Text style={styles.fieldHint}>Isi email untuk kirim undangan lewat email, atau kosongkan untuk dapat tautan saja.</Text>
      <View style={styles.inlineForm}>
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
      </View>
      {!!error && <Text style={styles.errorText}>{error}</Text>}
      {!!invite && (
        <View style={styles.inviteLinkRow}>
          <Text style={styles.inviteLinkText} numberOfLines={1}>
            {invite.invite_url}
          </Text>
          <Pressable style={styles.smallButton} onPress={handleCopy}>
            <Feather name={copied ? "check" : "copy"} size={12} color={colors.ink} />
            <Text style={styles.smallButtonLabel}>{copied ? "Tersalin" : "Salin"}</Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

function TeamNameHeader({ team, isAdmin, onRenamed }) {
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
      const fresh = await renameTeam(team.id, name.trim());
      onRenamed(fresh);
    } finally {
      setSaving(false);
      setEditing(false);
    }
  }

  if (editing) {
    return (
      <View style={styles.inlineForm}>
        <TextInput style={styles.input} value={name} onChangeText={setName} autoFocus />
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
  return (
    <View style={styles.memberRow}>
      <View style={styles.avatar}>
        <Text style={styles.avatarLabel}>{initialsOf(member.name)}</Text>
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.memberName}>
          {member.name}
          {isSelf && " (Anda)"}
        </Text>
        <Text style={styles.memberEmail}>{member.email}</Text>
      </View>
      <View style={[styles.roleBadge, member.team_role === "admin" && styles.roleBadgeAdmin]}>
        <Text style={[styles.roleBadgeLabel, member.team_role === "admin" && styles.roleBadgeLabelAdmin]}>
          {member.team_role === "admin" ? "Admin" : "Member"}
        </Text>
      </View>
      {isAdmin && !isSelf && (
        <>
          <Pressable
            style={styles.smallButton}
            onPress={() => onRoleChange(member.id, member.team_role === "admin" ? "member" : "admin")}
          >
            <Text style={styles.smallButtonLabel}>
              {member.team_role === "admin" ? "Jadikan Member" : "Jadikan Admin"}
            </Text>
          </Pressable>
          <Pressable style={styles.dangerLink} onPress={() => onRemove(member.id)} hitSlop={8}>
            <Feather name="user-x" size={14} color={colors.danger} />
          </Pressable>
        </>
      )}
    </View>
  );
}

function TeamCard({ team, members, isAdmin, myId, onRefresh }) {
  const [confirmLeaveOpen, setConfirmLeaveOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [leaveError, setLeaveError] = useState("");

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

  function handleRemove(userId) {
    removeTeamMember(userId).then(onRefresh);
  }

  function handleRoleChange(userId, role) {
    updateTeamMemberRole(userId, role).then(onRefresh);
  }

  return (
    <>
      <View style={styles.card}>
        <TeamNameHeader team={team} isAdmin={isAdmin} onRenamed={onRefresh} />
        <Text style={styles.cardBody}>{members.length} anggota</Text>

        <View style={styles.divider} />

        <View style={{ gap: spacing.sm }}>
          {members.map((m) => (
            <MemberRow
              key={m.id}
              member={m}
              isAdmin={isAdmin}
              isSelf={m.id === myId}
              onRemove={handleRemove}
              onRoleChange={handleRoleChange}
            />
          ))}
        </View>

        {isAdmin && (
          <>
            <View style={styles.divider} />
            <InviteBox />
          </>
        )}

        <View style={styles.divider} />
        {!!leaveError && <Text style={styles.errorText}>{leaveError}</Text>}
        <Pressable style={styles.dangerLinkRow} onPress={() => setConfirmLeaveOpen(true)}>
          <Feather name="log-out" size={13} color={colors.danger} />
          <Text style={styles.dangerLinkLabel}>Keluar dari Team</Text>
        </Pressable>
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
    // Refresh /auth/me too — user.team_id/team_role just changed.
    setTeamData({ team, members: [{ ...user, team_role: "admin" }] });
    updateUser({ ...user, team_id: team.id, team_role: "admin" });
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.scrollContent}>
      <View style={styles.content}>
        <Text style={styles.eyebrow}>MENU</Text>
        <Text style={styles.title}>Team</Text>
        <Text style={styles.description}>Kelola anggota team dan bagikan hasil rapat.</Text>

        {status === "loading" && (
          <View style={styles.stateBox}>
            <ActivityIndicator color={colors.gold} />
          </View>
        )}
        {status === "error" && <Text style={styles.errorText}>{error}</Text>}

        {status === "done" && !teamData && plan === "team" && <CreateTeamCard onCreated={handleCreated} />}
        {status === "done" && !teamData && plan !== "team" && <UpsellCard />}
        {status === "done" && teamData && (
          <TeamCard
            team={teamData.team}
            members={teamData.members}
            isAdmin={teamData.members.find((m) => m.id === user?.id)?.team_role === "admin"}
            myId={user?.id}
            onRefresh={load}
          />
        )}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  scrollContent: { alignItems: "center", padding: spacing.lg },
  content: { gap: spacing.sm, maxWidth: 720, width: "100%" },
  eyebrow: { ...type.eyebrow, color: colors.inkFaint },
  title: { ...type.h1, fontSize: 24, color: colors.ink, marginTop: 4 },
  description: { ...type.body, color: colors.inkSoft, marginTop: 2, marginBottom: spacing.xl },
  stateBox: { alignItems: "center", padding: spacing.xl },
  errorText: { ...type.small, color: colors.danger, marginTop: 4 },

  card: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.lg,
    gap: spacing.sm,
    ...shadow.card,
  },
  iconWrap: {
    width: 44,
    height: 44,
    borderRadius: radius.sm,
    backgroundColor: colors.goldSoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xs,
  },
  cardTitle: { ...type.h2, color: colors.ink },
  cardBody: { ...type.body, color: colors.inkFaint, lineHeight: 20 },

  inlineForm: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs },
  input: {
    flex: 1,
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
  primaryButton: {
    backgroundColor: colors.gold,
    borderRadius: radius.sm,
    paddingVertical: 9,
    paddingHorizontal: spacing.lg,
    alignItems: "center",
    justifyContent: "center",
  },
  buttonDisabled: { opacity: 0.5 },
  primaryButtonLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },

  divider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.xs },

  teamNameRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  teamName: { ...type.h2, color: colors.ink },

  memberRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  avatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.ink,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarLabel: { color: colors.white, fontWeight: "700", fontSize: 13 },
  memberName: { ...type.bodyMedium, fontWeight: "600", color: colors.ink },
  memberEmail: { ...type.small, color: colors.inkFaint },
  roleBadge: { backgroundColor: colors.surfaceSunken, borderRadius: radius.pill, paddingVertical: 3, paddingHorizontal: 10 },
  roleBadgeAdmin: { backgroundColor: colors.goldSoft },
  roleBadgeLabel: { ...type.small, fontWeight: "700", color: colors.inkFaint },
  roleBadgeLabelAdmin: { color: colors.goldDeep },

  smallButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.pill,
    paddingVertical: 6,
    paddingHorizontal: spacing.sm,
    backgroundColor: colors.surface,
  },
  smallButtonLabel: { ...type.small, fontWeight: "600", color: colors.ink },
  dangerLink: { padding: 4 },
  dangerLinkRow: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start" },
  dangerLinkLabel: { ...type.small, fontWeight: "600", color: colors.danger },

  fieldLabel: { ...type.eyebrow, color: colors.inkFaint },
  fieldHint: { ...type.small, color: colors.inkFaint, marginTop: 2 },
  inviteBox: { gap: 2 },
  inviteLinkRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginTop: spacing.sm,
    backgroundColor: colors.surfaceSunken,
    borderRadius: radius.sm,
    padding: spacing.sm,
  },
  inviteLinkText: { ...type.small, color: colors.inkSoft, flex: 1 },

  modalOverlay: {
    flex: 1,
    backgroundColor: "rgba(27,31,43,0.45)",
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.lg,
  },
  modalCard: {
    maxWidth: 360,
    width: "100%",
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.lg,
    alignItems: "center",
    gap: spacing.sm,
  },
  modalIconWrap: {
    width: 44,
    height: 44,
    borderRadius: radius.sm,
    backgroundColor: colors.dangerSoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xs,
  },
  modalTitle: { ...type.h2, color: colors.ink, textAlign: "center" },
  modalBody: { ...type.body, color: colors.inkSoft, textAlign: "center", lineHeight: 19 },
  modalActions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, alignSelf: "stretch" },
  modalCancelButton: {
    flex: 1,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingVertical: 11,
    alignItems: "center",
  },
  modalCancelLabel: { ...type.bodyMedium, fontWeight: "600", color: colors.ink },
  modalConfirmButton: {
    flex: 1,
    backgroundColor: colors.danger,
    borderRadius: radius.sm,
    paddingVertical: 11,
    alignItems: "center",
  },
  modalConfirmLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.white },
});
