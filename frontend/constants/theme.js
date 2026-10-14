// token desain: tinta navy dari logo, emas hangat sebagai satu-satunya aksen (untuk yang harus menarik mata) dan latar
// kertas lembut, bukan putih murni

export const colors = {
  ink: "#1B1F2B",
  inkSoft: "#4A5064",
  inkFaint: "#8A8F9E",

  bg: "#F6F4EE",
  surface: "#FFFFFF",
  surfaceSunken: "#F1EEE4",
  border: "#ECE8DC",

  gold: "#E3B54A",
  goldSoft: "#F6E7C4",
  goldDeep: "#8A6416",

  success: "#1F9254",
  successSoft: "#DEF3E6",
  info: "#3B6FE0",
  infoSoft: "#E4EBFC",
  danger: "#D6484A",
  dangerSoft: "#FBE4E4",

  white: "#FFFFFF",
};

// Lebih lega dari versi pertama (md 12, lg 16, xl 24): setiap jarak dan padding
// yang memakai token ikut membesar, yaitu sebagian besar aplikasi.
export const spacing = {
  xs: 4,
  sm: 8,
  md: 14,
  lg: 20,
  xl: 28,
  xxl: 36,
  xxxl: 52,
};

export const radius = {
  sm: 10,
  md: 14,
  lg: 20,
  pill: 999,
};

// Dimuat di app/_layout.jsx; sisanya fallback sistem biasa.
export const FONT_FAMILY = 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';

export const type = {
  display: { fontFamily: FONT_FAMILY, fontSize: 32, fontWeight: "700", letterSpacing: -0.6 },
  h1: { fontFamily: FONT_FAMILY, fontSize: 24, fontWeight: "700", letterSpacing: -0.4 },
  h2: { fontFamily: FONT_FAMILY, fontSize: 17, fontWeight: "600", letterSpacing: -0.1 },
  body: { fontFamily: FONT_FAMILY, fontSize: 14.5, fontWeight: "400", lineHeight: 22 },
  bodyMedium: { fontFamily: FONT_FAMILY, fontSize: 14.5, fontWeight: "500", lineHeight: 22 },
  small: { fontFamily: FONT_FAMILY, fontSize: 12.5, fontWeight: "400", lineHeight: 18 },
  eyebrow: { fontFamily: FONT_FAMILY, fontSize: 11, fontWeight: "600", letterSpacing: 0.8, textTransform: "uppercase" },
  stat: { fontFamily: FONT_FAMILY, fontSize: 28, fontWeight: "700", letterSpacing: -0.6 },
};

// Lembut dan lebar, bukan tepi gelap yang rapat: kartu terlihat sedikit melayang dari halaman.
export const shadow = {
  card: {
    shadowColor: "#1B1F2B",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.05,
    shadowRadius: 14,
    elevation: 2,
  },
};
