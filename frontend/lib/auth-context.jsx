import { createContext, useContext, useEffect, useState } from "react";

import { getMe } from "./api";

// siapa yang login, untuk seluruh aplikasi. Mengecek GET /auth/me sekali saat mount (cookie sesi ikut, lihat apiFetch) dan
// (app)/_layout.jsx memakai `status` untuk mengalihkan ke /login
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

  // Menyegarkan user yang di-cache setelah edit profil sendiri (kolom "Nama"
  // di Pengaturan) - setter yang sama dengan signIn, hanya dinamai sesuai kegunaannya di sini.
  function updateUser(u) {
    setUser(u);
  }

  return <AuthContext.Provider value={{ user, status, signIn, signOut, updateUser }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth() must be used inside <AuthProvider>");
  return ctx;
}
