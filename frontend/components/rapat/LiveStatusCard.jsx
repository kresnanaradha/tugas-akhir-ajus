import { Feather } from "@expo/vector-icons";
import { useEffect, useRef } from "react";
import { ActivityIndicator, Animated, Pressable, Text, View } from "react-native";

import { colors } from "@/constants/theme";
import { formatElapsed } from "@/lib/transcript";

import { styles } from "./styles";

const STEPS = [
  { key: "joining", label: "Bergabung" },
  { key: "recording", label: "Merekam" },
  { key: "processing", label: "Memproses" },
];
const STEP_INDEX = { queued: 0, joining: 0, recording: 1, stopping: 1, processing: 2 };

function PulsingDot() {
  const opacity = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.3, duration: 700, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 1, duration: 700, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [opacity]);
  return <Animated.View style={[styles.pulseDot, { opacity }]} />;
}

// tampilan saat bot masih menunggu, bergabung, merekam, atau rekamannya sedang diproses
export function LiveStatusCard({ liveStatus, elapsed, canEdit, onStop }) {
  const stepIndex = STEP_INDEX[liveStatus] ?? 0;
  return (
    <View style={styles.liveCard}>
      <View style={styles.stepper}>
        {STEPS.map((step, i) => (
          <View key={step.key} style={styles.stepItemWrap}>
            <View style={styles.stepItem}>
              <View style={[styles.stepDot, i <= stepIndex && styles.stepDotActive]} />
              <Text style={[styles.stepLabel, i === stepIndex && styles.stepLabelActive]}>{step.label}</Text>
            </View>
            {i < STEPS.length - 1 && <View style={[styles.stepLine, i < stepIndex && styles.stepLineActive]} />}
          </View>
        ))}
      </View>

      {liveStatus === "recording" || liveStatus === "stopping" ? (
        <View style={styles.liveCenter}>
          <View style={styles.liveStatusRow}>
            <PulsingDot />
            <Text style={styles.liveStatusText}>
              {liveStatus === "stopping" ? "Menghentikan rekaman..." : "Sedang merekam"}
            </Text>
          </View>
          <Text style={styles.liveTimer}>{formatElapsed(elapsed)}</Text>
        </View>
      ) : (
        <View style={styles.liveCenter}>
          <ActivityIndicator color={colors.gold} size="large" />
          <Text style={styles.liveStatusText}>
            {liveStatus === "queued"
              ? "Menunggu perekam yang kosong..."
              : liveStatus === "joining"
                ? "Bot sedang bergabung ke rapat..."
                : "Memproses transkripsi & ringkasan..."}
          </Text>
        </View>
      )}

      {liveStatus === "recording" && canEdit && (
        <Pressable style={styles.stopButton} onPress={onStop}>
          <Feather name="square" size={13} color={colors.white} />
          <Text style={styles.stopButtonLabel}>Stop Rekam</Text>
        </Pressable>
      )}

      <View style={styles.liveInfoBox}>
        <Feather name="info" size={13} color={colors.goldDeep} />
        <Text style={styles.liveInfoText}>
          Anda bisa tinggalkan halaman ini, proses tetap berjalan di server. Cek lagi lewat daftar Rapat kapan
          saja.
        </Text>
      </View>
    </View>
  );
}
