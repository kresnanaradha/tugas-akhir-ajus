import { Slot } from "expo-router";
import { StyleSheet, View } from "react-native";

import { colors } from "@/constants/theme";
import { Sidebar } from "@/components/Sidebar";
import { TopBar } from "@/components/TopBar";

export default function AppLayout() {
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
