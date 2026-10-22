import { useSelector } from "react-redux";
import { selectPermissions } from "@/store/slices/authSlice";

/** UX-only permission checks; the Flask API enforces every action. */
export function usePermissions() {
  const permissions = useSelector(selectPermissions);
  const set = new Set(permissions);
  return {
    permissions,
    can: (...required) => required.every((p) => set.has(p)),
    canAny: (...options) => options.some((p) => set.has(p)),
    /** Nav items and guards declare either one `permission` or a list of `anyOf`. */
    allows: ({ permission, anyOf }) =>
      (!permission || set.has(permission)) && (!anyOf || anyOf.some((p) => set.has(p))),
  };
}
