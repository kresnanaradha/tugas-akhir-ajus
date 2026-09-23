import { Redirect, Slot } from "expo-router";
import { ActivityIndicator, StyleSheet, View } from "react-native";

import { colors } from "@/constants/theme";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";
import { useAuth } from "@/lib/auth-context";

export default function AppLayout() {
  const { status } = useAuth();

  // Every screen under (app)/ requires a session — checked once here rather
  // than in each screen, since they all share this layout. A direct
  // navigation to e.g. /dashboard with no session bounces to /login instead
  // of rendering the shell around an empty/erroring page.
  if (status === "loading") {
    return (
      <View style={[styles.root, { alignItems: "center", justifyContent: "center" }]}>
        <ActivityIndicator color={colors.gold} />
      </View>
    );
  }
  if (status === "anonymous") {
    return <Redirect href="/login" />;
  }

  return (
    <View style={styles.root}>
      <Sidebar />
      <View style={styles.content}>
        <TopBar />
        <View style={styles.body}>
          <Slot />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, flexDirection: "row", backgroundColor: colors.bg },
  content: { flex: 1 },
  body: { flex: 1 },
});
