import { Feather } from "@expo/vector-icons";
import { useState } from "react";
import { Pressable, StyleSheet, TextInput, View } from "react-native";

import { colors } from "@/constants/theme";

// kolom password dengan ikon mata untuk melihat atau menyembunyikan isinya. Dipakai seperti TextInput biasa, stylenya
// sama: properti tata letak (flex, width, margin) dipindah ke pembungkus supaya kolom tetap pas di barisnya
const LAYOUT_KEYS = ["flex", "flexGrow", "flexShrink", "flexBasis", "width", "minWidth", "alignSelf", "marginTop", "marginBottom"];

export function PasswordInput({ style, ...props }) {
  const [visible, setVisible] = useState(false);
  const flat = StyleSheet.flatten(style) || {};
  const wrapStyle = {};
  const inputStyle = {};
  for (const [key, value] of Object.entries(flat)) (LAYOUT_KEYS.includes(key) ? wrapStyle : inputStyle)[key] = value;

  // paddingHorizontal/padding mengalahkan paddingRight di react-native-web, jadi sisi kiri dan kanan ditulis ulang satu per satu
  // dan sisi kanan diberi ruang untuk ikon mata
  const padH = flat.paddingHorizontal ?? flat.padding ?? 14;
  const padV = flat.paddingVertical ?? flat.padding;
  for (const key of ["padding", "paddingHorizontal", "paddingVertical", "paddingLeft", "paddingRight"]) delete inputStyle[key];
  inputStyle.paddingLeft = flat.paddingLeft ?? padH;
  inputStyle.paddingRight = (flat.paddingRight ?? padH) + 30;
  if (padV !== undefined) {
    inputStyle.paddingTop = flat.paddingTop ?? padV;
    inputStyle.paddingBottom = flat.paddingBottom ?? padV;
  }

  return (
    <View style={[styles.wrap, wrapStyle]}>
      <TextInput {...props} secureTextEntry={!visible} style={[inputStyle, styles.input]} />
      <Pressable
        style={styles.eye}
        onPress={() => setVisible((v) => !v)}
        accessibilityRole="button"
        accessibilityLabel={visible ? "Sembunyikan password" : "Tampilkan password"}
      >
        <Feather name={visible ? "eye-off" : "eye"} size={16} color={colors.inkFaint} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { justifyContent: "center" },
  input: { width: "100%" },
  eye: { position: "absolute", right: 0, top: 0, bottom: 0, width: 40, alignItems: "center", justifyContent: "center" },
});
