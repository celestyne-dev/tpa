import { cn } from "@/utils/format";

const sizes = { narrow: "max-w-3xl", default: "max-w-6xl", wide: "max-w-7xl" };

export function Container({ as: Component = "div", size = "default", className, ...props }) {
  return (
    <Component className={cn("mx-auto w-full px-5 sm:px-8", sizes[size], className)} {...props} />
  );
}
