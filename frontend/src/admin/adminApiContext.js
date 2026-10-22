import { createContext, useContext } from "react";

export const AdminApiContext = createContext(null);

export function useAdminApi() {
  return useContext(AdminApiContext);
}
