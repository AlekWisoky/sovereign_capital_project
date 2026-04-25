import AsyncStorage from "@react-native-async-storage/async-storage";

export type AddressBookEntry = { name: string; address: string };

const KEY = "vax_address_book_v2";

function safeParse(s: string): unknown {
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

export async function loadAddressBook(): Promise<AddressBookEntry[]> {
  const raw = await AsyncStorage.getItem(KEY);
  if (!raw) return [];
  const parsed = safeParse(raw);
  if (!Array.isArray(parsed)) return [];
  const out: AddressBookEntry[] = [];
  for (const v of parsed) {
    if (typeof v !== "object" || v === null) continue;
    const o = v as Record<string, unknown>;
    const name = typeof o.name === "string" ? o.name : "";
    const address = typeof o.address === "string" ? o.address : "";
    if (!address) continue;
    out.push({ name, address });
  }
  return out;
}

export async function saveAddressBook(entries: readonly AddressBookEntry[]): Promise<void> {
  await AsyncStorage.setItem(KEY, JSON.stringify(entries));
}
