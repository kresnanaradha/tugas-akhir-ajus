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

// More air than the first version (md 12, lg 16, xl 24): every gap and padding
// that uses a token grows with it, which is most of the app.
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

// Loaded in app/_layout.jsx; the rest is the usual system fallback.
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

// Soft and wide instead of a tight dark edge: cards float a little off the page.
export const shadow = {
  card: {
    shadowColor: "#1B1F2B",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.05,
    shadowRadius: 14,
    elevation: 2,
  },
};
