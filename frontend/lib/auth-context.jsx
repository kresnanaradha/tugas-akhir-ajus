import { createContext, useContext, useEffect, useState } from "react";

import { getMe } from "./api";

// Single source of truth for "who's logged in" across the app — Sidebar/
// TopBar read the user from here instead of the old mock-data.js stand-in,
// and (app)/_layout.jsx uses `status` to redirect to /login when there's no
// session. Checks GET /auth/me once on mount (the session cookie, if any,
// rides along automatically — see lib/api.js's apiFetch) rather than each
// screen re-checking independently.
const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState("loading"); // loading | authenticated | anonymous

  useEffect(() => {
    getMe()
      .then((u) => {
        setUser(u);
        setStatus("authenticated");
      })
      .catch(() => setStatus("anonymous"));
  }, []);

  function signIn(u) {
    setUser(u);
    setStatus("authenticated");
  }

  function signOut() {
    setUser(null);
    setStatus("anonymous");
  }

  return <AuthContext.Provider value={{ user, status, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() must be used inside <AuthProvider>");
  return ctx;
}
