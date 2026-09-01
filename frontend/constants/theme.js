// Design tokens for Notulis. Palette is grounded in the product's own
// identity: navy ink from the logo mark, warm gold as the single accent
// (the "highlighter" color — used for the one thing on a screen that should
// draw the eye), and a soft paper background instead of pure white.

export const colors = {
  ink: "#1B1F2B",
  inkSoft: "#4A5064",
  inkFaint: "#8A8F9E",

  bg: "#F6F4EE",
  surface: "#FFFFFF",
  surfaceSunken: "#F1EEE4",
  border: "#E4E0D2",

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

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
};

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  pill: 999,
};

export const type = {
  display: { fontSize: 30, fontWeight: "700", letterSpacing: -0.4 },
  h1: { fontSize: 22, fontWeight: "700", letterSpacing: -0.2 },
  h2: { fontSize: 17, fontWeight: "600" },
  body: { fontSize: 14.5, fontWeight: "400" },
  bodyMedium: { fontSize: 14.5, fontWeight: "500" },
  small: { fontSize: 12.5, fontWeight: "400" },
  eyebrow: { fontSize: 11, fontWeight: "600", letterSpacing: 0.6 },
  stat: { fontSize: 28, fontWeight: "700", letterSpacing: -0.5 },
};

export const shadow = {
  card: {
    shadowColor: "#1B1F2B",
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 3,
    elevation: 1,
  },
};
