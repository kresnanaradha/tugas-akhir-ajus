import { Feather } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, shadow, spacing, type } from "@/constants/theme";
import { joinTeam, previewTeamInvite } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

// Landing page for a team invite link (POST /teams/invite's invite_url) —
// shows which team before committing, then POSTs /teams/join. Lives under
// (app)/ (needs login) same as team.jsx; an anonymous visitor gets bounced
// to /login by the layout first, same as every other (app)/ route.
export default function JoinTeamScreen() {
  const { token } = useLocalSearchParams();
  const { user } = useAuth();
  const [status, setStatus] = useState("loading"); // loading | ready | joining | error | done
  const [teamName, setTeamName] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    previewTeamInvite(token)
      .then((data) => {
        setTeamName(data.team_name);
        setStatus("ready");
      })
      .catch((e) => {
        setError(e.message || "Tautan undangan tidak valid");
        setStatus("error");
      });
  }, [token]);

  async function handleJoin() {
    setStatus("joining");
    setError("");
    try {
      await joinTeam(token);
      setStatus("done");
      setTimeout(() => router.replace("/team"), 1200);
    } catch (e) {
      setError(e.message || "Gagal bergabung ke team");
      setStatus("ready");
    }
  }

  return (
    <View style={styles.screen}>
      <View style={styles.card}>
        <View style={styles.iconWrap}>
          <Feather name="users" size={22} color={colors.goldDeep} />
        </View>

        {status === "loading" && <ActivityIndicator color={colors.gold} />}

        {status === "error" && (
          <>
            <Text style={styles.title}>Undangan Tidak Valid</Text>
            <Text style={styles.body}>{error}</Text>
          </>
        )}

        {(status === "ready" || status === "joining") && (
          <>
            <Text style={styles.title}>Gabung ke Team "{teamName}"?</Text>
            <Text style={styles.body}>
              {user?.team_id
                ? "Anda sudah tergabung dalam team lain — keluar dulu dari halaman Team sebelum gabung ke team baru."
                : `Anda akan bergabung sebagai member. Rapat yang dibagikan anggota lain akan terlihat di daftar Rapat Anda.`}
            </Text>
            {!!error && <Text style={styles.errorText}>{error}</Text>}
            <Pressable
              style={[styles.primaryButton, (status === "joining" || user?.team_id) && styles.buttonDisabled]}
              disabled={status === "joining" || !!user?.team_id}
              onPress={handleJoin}
            >
              {status === "joining" ? <ActivityIndicator size="small" color={colors.ink} /> : <Text style={styles.primaryButtonLabel}>Gabung Team</Text>}
            </Pressable>
          </>
        )}

        {status === "done" && (
          <>
            <Feather name="check-circle" size={20} color={colors.success} />
            <Text style={styles.title}>Berhasil Bergabung</Text>
            <Text style={styles.body}>Mengarahkan ke halaman Team...</Text>
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg },
  card: {
    maxWidth: 420,
    width: "100%",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    padding: spacing.xl,
    alignItems: "center",
    gap: spacing.sm,
    ...shadow.card,
  },
  iconWrap: {
    width: 48,
    height: 48,
    borderRadius: radius.sm,
    backgroundColor: colors.goldSoft,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.xs,
  },
  title: { ...type.h2, color: colors.ink, textAlign: "center" },
  body: { ...type.body, color: colors.inkSoft, textAlign: "center", lineHeight: 20 },
  errorText: { ...type.small, color: colors.danger, textAlign: "center" },
  primaryButton: {
    backgroundColor: colors.gold,
    borderRadius: radius.sm,
    paddingVertical: 10,
    paddingHorizontal: spacing.xl,
    alignItems: "center",
    justifyContent: "center",
    marginTop: spacing.sm,
  },
  buttonDisabled: { opacity: 0.5 },
  primaryButtonLabel: { ...type.bodyMedium, fontWeight: "700", color: colors.ink },
});
