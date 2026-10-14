import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";

import { useEffect } from "react";

import { FONT_FAMILY } from "@/constants/theme";
import { AuthProvider } from "@/lib/auth-context";

// Inter for the whole web app: the stylesheet is added once, and body gets the family
// so text that does not use a type token still inherits it.
function useInterFont() {
  useEffect(() => {
    if (typeof document === "undefined" || document.getElementById("notulis-font")) return;
    const link = document.createElement("link");
    link.id = "notulis-font";
    link.rel = "stylesheet";
    link.href = "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap";
    document.head.appendChild(link);
    document.body.style.fontFamily = FONT_FAMILY;
    document.body.style.webkitFontSmoothing = "antialiased";
  }, []);
}

export default function RootLayout() {
  useInterFont();
  return (
    <AuthProvider>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="login" />
        <Stack.Screen name="(app)" />
      </Stack>
    </AuthProvider>
  );
}
