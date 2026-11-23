import { Redirect } from "expo-router";
import { ActivityIndicator, View } from "react-native";

import { colors } from "@/constants/theme";
import { useAuth } from "@/lib/auth-context";

export default function Index() {
  const { status, user } = useAuth();

  if (status === "loading") {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg }}>
        <ActivityIndicator color={colors.gold} />
      </View>
    );
  }

  // Super Admin hanya mengelola sistem, jadi halaman awalnya Statistik
  const home = user?.role === "super_admin" ? "/admin" : "/dashboard";
  return <Redirect href={status === "authenticated" ? home : "/login"} />;
}
