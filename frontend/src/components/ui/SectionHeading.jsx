import { cn } from "@/utils/format";

export function SectionHeading({
  eyebrow,
  title,
  description,
  align = "left",
  as: Heading = "h2",
  id,
  invert = false,
  className,
  action,
}) {
  const centered = align === "center";
  return (
    <div
      className={cn(
        "flex flex-col gap-6",
        Boolean(action) && !centered && "md:flex-row md:items-end md:justify-between",
        centered && "items-center text-center",
        className,
      )}
    >
      <div className={cn("max-w-2xl", centered && "mx-auto")}>
        {eyebrow && (
          <p
            className={cn(
              "mb-3 text-sm font-semibold tracking-[0.14em] uppercase",
              invert ? "text-gold-300" : "text-sage-700",
            )}
          >
            {eyebrow}
          </p>
        )}
        <Heading
          id={id}
          className={cn(
            "text-3xl font-medium sm:text-4xl lg:text-[2.75rem]",
            invert && "text-ivory",
          )}
        >
          {title}
        </Heading>
        {description && (
          <p className={cn("mt-4 text-lg", invert ? "text-sand" : "text-muted")}>{description}</p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
