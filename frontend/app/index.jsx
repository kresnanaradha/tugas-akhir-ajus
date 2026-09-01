import { Redirect } from "expo-router";

// No auth wired up yet (POC scope) — always sends to the login screen,
// which itself links straight into the dashboard for demo purposes.
export default function Index() {
  return <Redirect href="/login" />;
}
