import React, { useEffect, useMemo, useState } from "react";
import { Modal, Pressable, Text, TextInput, View } from "react-native";
import { theme } from "../utils/theme";
import { clampDecimals, formatUnits } from "../utils/amounts";
import { fetchTokenMeta, type Eip1193Provider } from "../utils/erc20";
import { isHexAddress, normalizeAddress } from "../utils/eth";
import { deleteTokenMeta, getTokenMeta, upsertTokenMeta } from "../state/tokenMeta";

type Props = {
  label: string;
  tokenAddress: string;
  rawValue: string;
  wcConnected?: boolean;
  wcProvider?: Eip1193Provider;
  // If true, renders a compact pill that opens the full helper UI.
  compact?: boolean;
};

export function TokenAmountDisplay({
  label,
  tokenAddress,
  rawValue,
  wcConnected,
  wcProvider,
  compact = false,
}: Props) {
  const token = useMemo(() => normalizeAddress(tokenAddress || "") || "", [tokenAddress]);
  const raw = String(rawValue || "0");

  const [metaDecimals, setMetaDecimals] = useState<number | null>(null);
  const [metaSymbol, setMetaSymbol] = useState<string>("");
  const [metaSource, setMetaSource] = useState<"chain" | "manual" | "none">("none");
  const [metaLoading, setMetaLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const [editing, setEditing] = useState(false);
  const [decDraft, setDecDraft] = useState("");
  const [symDraft, setSymDraft] = useState("");

  useEffect(() => {
    (async () => {
      setMetaDecimals(null);
      setMetaSymbol("");
      setMetaSource("none");
      setEditing(false);
      setDecDraft("");
      setSymDraft("");

      if (!isHexAddress(token)) return;

      setMetaLoading(true);
      try {
        const cached = await getTokenMeta(token);
        if (cached) {
          setMetaDecimals(clampDecimals(cached.decimals));
          setMetaSymbol(String(cached.symbol || ""));
          setMetaSource(cached.source);
        }
        if (!cached && wcConnected && wcProvider) {
          const m = await fetchTokenMeta(wcProvider, token);
          if (typeof m.decimals === "number") {
            setMetaDecimals(clampDecimals(m.decimals));
            setMetaSymbol(String(m.symbol || ""));
            setMetaSource("chain");
            await upsertTokenMeta({ address: token, decimals: m.decimals, symbol: m.symbol, source: "chain" });
          }
        }
      } catch {
        // best-effort
      } finally {
        setMetaLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, wcConnected]);

  const human = useMemo(() => {
    if (metaDecimals === null) return "";
    try {
      return formatUnits(raw, metaDecimals, 8);
    } catch {
      return "";
    }
  }, [raw, metaDecimals]);

  const headline = metaDecimals !== null
    ? `${human || "0"}${metaSymbol ? ` ${metaSymbol}` : ""}`
    : raw;

  async function refreshFromChain() {
    if (!wcConnected || !wcProvider || !isHexAddress(token)) return;
    setMetaLoading(true);
    try {
      const m = await fetchTokenMeta(wcProvider, token);
      if (typeof m.decimals === "number") {
        setMetaDecimals(clampDecimals(m.decimals));
        setMetaSymbol(String(m.symbol || ""));
        setMetaSource("chain");
        await upsertTokenMeta({ address: token, decimals: m.decimals, symbol: m.symbol, source: "chain" });
      }
    } catch {
      // ignore
    } finally {
      setMetaLoading(false);
    }
  }

  async function saveManual() {
    if (!isHexAddress(token)) return;
    const d = clampDecimals(parseInt(decDraft || "0", 10));
    const s = String(symDraft || "").trim();
    await upsertTokenMeta({ address: token, decimals: d, symbol: s || undefined, source: "manual" });
    setMetaDecimals(d);
    setMetaSymbol(s);
    setMetaSource("manual");
    setEditing(false);
  }

  async function clearMeta() {
    if (!isHexAddress(token)) return;
    await deleteTokenMeta(token);
    setMetaDecimals(null);
    setMetaSymbol("");
    setMetaSource("none");
    setEditing(false);
    setDecDraft("");
    setSymDraft("");
  }

  const core = (
    <View style={{ marginTop: 10 }}>
      <Text style={{ color: theme.sub }}>{label}</Text>
      <Text style={{ color: theme.text, fontSize: 18, fontWeight: "900", marginTop: 2 }}>{headline}</Text>
      <Text style={{ color: theme.sub, marginTop: 2 }}>raw: {raw}</Text>
      <Text style={{ color: theme.sub, marginTop: 4 }}>
        meta: {metaDecimals !== null ? `${metaDecimals}d` : "unknown"}{metaSymbol ? ` · ${metaSymbol}` : ""}{metaSource !== "none" ? ` (${metaSource})` : ""}
      </Text>

      <View style={{ flexDirection: "row", gap: 10, marginTop: 10 }}>
        <Pressable
          onPress={refreshFromChain}
          disabled={!wcConnected || metaLoading || !isHexAddress(token)}
          style={{
            flex: 1,
            paddingVertical: 10,
            borderRadius: 14,
            borderWidth: 1,
            borderColor: theme.border,
            backgroundColor: theme.card2,
            opacity: (!wcConnected || metaLoading || !isHexAddress(token)) ? 0.55 : 1,
            alignItems: "center",
          }}
        >
          <Text style={{ color: theme.text, fontWeight: "900" }}>{metaLoading ? "…" : "Refresh"}</Text>
        </Pressable>

        <Pressable
          onPress={() => {
            setEditing(!editing);
            setDecDraft(metaDecimals !== null ? String(metaDecimals) : "");
            setSymDraft(metaSymbol || "");
          }}
          disabled={!isHexAddress(token)}
          style={{
            flex: 1,
            paddingVertical: 10,
            borderRadius: 14,
            borderWidth: 1,
            borderColor: theme.border,
            backgroundColor: theme.card2,
            opacity: !isHexAddress(token) ? 0.55 : 1,
            alignItems: "center",
          }}
        >
          <Text style={{ color: theme.text, fontWeight: "900" }}>{editing ? "Close" : "Edit"}</Text>
        </Pressable>
      </View>

      {editing ? (
        <View style={{ marginTop: 10, padding: 12, borderRadius: 14, borderWidth: 1, borderColor: theme.border, backgroundColor: theme.card2 }}>
          <Text style={{ color: theme.sub }}>Decimals</Text>
          <TextInput
            value={decDraft}
            onChangeText={setDecDraft}
            keyboardType="numeric"
            style={{ marginTop: 6, padding: 10, borderRadius: 12, borderWidth: 1, borderColor: theme.border, color: theme.text, backgroundColor: theme.bg }}
          />
          <Text style={{ color: theme.sub, marginTop: 10 }}>Symbol (optional)</Text>
          <TextInput
            value={symDraft}
            onChangeText={setSymDraft}
            autoCapitalize="characters"
            style={{ marginTop: 6, padding: 10, borderRadius: 12, borderWidth: 1, borderColor: theme.border, color: theme.text, backgroundColor: theme.bg }}
          />
          <View style={{ flexDirection: "row", gap: 10, marginTop: 12 }}>
            <Pressable
              onPress={saveManual}
              style={{ flex: 1, paddingVertical: 10, borderRadius: 12, backgroundColor: theme.accent, alignItems: "center" }}
            >
              <Text style={{ color: "white", fontWeight: "900" }}>Save</Text>
            </Pressable>
            <Pressable
              onPress={clearMeta}
              style={{ flex: 1, paddingVertical: 10, borderRadius: 12, backgroundColor: theme.danger, alignItems: "center" }}
            >
              <Text style={{ color: "white", fontWeight: "900" }}>Clear</Text>
            </Pressable>
          </View>
        </View>
      ) : null}
    </View>
  );

  if (!compact) return core;

  return (
    <>
      <Pressable
        onPress={() => setOpen(true)}
        style={{
          marginTop: 10,
          paddingVertical: 10,
          paddingHorizontal: 12,
          borderRadius: 999,
          borderWidth: 1,
          borderColor: theme.border,
          backgroundColor: theme.card2,
        }}
      >
        <Text style={{ color: theme.sub, fontWeight: "700" }}>{label}</Text>
        <Text style={{ color: theme.text, fontWeight: "900" }}>{headline}</Text>
      </Pressable>

      <Modal visible={open} animationType="slide" transparent>
        <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.55)", justifyContent: "flex-end" }}>
          <View style={{ backgroundColor: theme.bg, borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: 16, borderWidth: 1, borderColor: theme.border }}>
            <Text style={{ color: theme.text, fontSize: 18, fontWeight: "900" }}>{label}</Text>
            <Text style={{ color: theme.sub, marginTop: 4 }}>{token ? token : "(token unknown)"}</Text>
            {core}
            <Pressable
              onPress={() => setOpen(false)}
              style={{ marginTop: 14, paddingVertical: 12, borderRadius: 16, backgroundColor: theme.glow, borderWidth: 1, borderColor: theme.border, alignItems: "center" }}
            >
              <Text style={{ color: theme.text, fontWeight: "900" }}>Close</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </>
  );
}
