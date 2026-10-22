import { Link } from "react-router";
import { buttonStyles } from "./buttonStyles";

export function Button({ variant, size, className, type = "button", ...props }) {
  return <button type={type} className={buttonStyles({ variant, size, className })} {...props} />;
}

/** Internal navigation styled as a button (uses React Router). */
export function ButtonLink({ variant, size, className, ...props }) {
  return <Link className={buttonStyles({ variant, size, className })} {...props} />;
}
