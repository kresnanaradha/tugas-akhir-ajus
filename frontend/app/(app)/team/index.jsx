import { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, Text, View } from "react-native";
import { CreateTeamPanel, UpsellPanel } from "@/components/team/CreateTeam";
import { TeamView } from "@/components/team/TeamView";
import { styles } from "@/components/team/styles";
import { colors } from "@/constants/theme";
import { getBillingStatus, getMyTeam } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

// sengaja tidak dibuat: sub-team bersarang dan kuota kursi (Team biaya tetap). Berbagi per rapat ada di rapat/[id].jsx

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
