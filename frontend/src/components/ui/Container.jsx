import { cn } from "@/utils/format";

// "page": the homepage's content width (1200px), between default (1152px) and wide (1280px).
const sizes = {
  narrow: "max-w-3xl",
  default: "max-w-6xl",
  page: "max-w-[75rem]",
  wide: "max-w-7xl",
};

export function Container({ as: Component = "div", size = "default", className, ...props }) {
  return (
    <Component className={cn("mx-auto w-full px-5 sm:px-8", sizes[size], className)} {...props} />
  );
}
