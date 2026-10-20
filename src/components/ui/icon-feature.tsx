import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** Icon + title + text block used in feature lists across pages. */
export function IconFeature({
  icon: Icon,
  title,
  children,
  className,
  headingLevel: Heading = "h3",
}: {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
  className?: string;
  headingLevel?: "h2" | "h3";
}) {
  return (
    <div className={cn("flex gap-5", className)}>
      <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-sage-100 text-sage-700">
        <Icon aria-hidden className="size-5" />
      </span>
      <div>
        <Heading className="font-serif text-xl font-medium">{title}</Heading>
        <div className="mt-2 text-muted">{children}</div>
      </div>
    </div>
  );
}
