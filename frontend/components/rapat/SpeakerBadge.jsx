import { Text, View } from "react-native";

import { speakerColor } from "@/lib/transcript";

import { styles } from "./styles";

export function SpeakerBadge({ speaker }) {
  const color = speakerColor(speaker);
  return (
    <View style={[styles.speakerBadge, { backgroundColor: `${color}22` }]}>
      <Text style={[styles.speakerBadgeLabel, { color }]}>{speaker}</Text>
    </View>
  );
}
