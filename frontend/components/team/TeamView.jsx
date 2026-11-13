// tampilan team yang sudah ada: nama team, undangan (admin), dan daftar anggota beserta perannya
import { Feather } from "@expo/vector-icons";
import { useState } from "react";
import { ActivityIndicator, Pressable, Text, TextInput, View } from "react-native";
import { ConfirmModal } from "@/components/ConfirmModal";
import { StatCard } from "@/components/StatCard";
import { styles } from "@/components/team/styles";
import { colors } from "@/constants/theme";
import { inviteToTeam, leaveTeam, removeTeamMember, renameTeam, updateTeamMemberRole } from "@/lib/api";
import { initialsOf } from "@/lib/format";

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

export function TeamView({ team, members, isAdmin, myId, onRefresh }) {
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

      <ConfirmModal
        visible={confirmLeaveOpen}
        title="Keluar dari team?"
        body="Anda tidak akan lagi melihat rapat yang dibagikan teammate. Rapat Anda sendiri tetap aman."
        confirmLabel="Ya, Keluar"
        busy={leaving}
        onCancel={() => setConfirmLeaveOpen(false)}
        onConfirm={handleLeave}
      />
    </>
  );
}
