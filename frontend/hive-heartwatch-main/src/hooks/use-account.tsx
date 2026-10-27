import { createContext, useContext } from "react";
import type { Me } from "@/lib/api";

export type AccountState = {
  user: Me | null;
  name: string;
  loading: boolean;
  refresh: () => Promise<void>;
};
export const AccountContext = createContext<AccountState>({
  user: null,
  name: "",
  loading: true,
  refresh: async () => {},
});
export const useAccount = () => useContext(AccountContext);
