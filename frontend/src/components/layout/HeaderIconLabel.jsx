/**
 * Tooltip for the header's icon buttons, shown on hover or keyboard focus. It is decorative
 * (aria-hidden) because the control's accessible name already includes the same words. No
 * inline label: the CMS menu beside these icons can be long, and labels would crowd it.
 */
export function HeaderIconLabel({ children }) {
  return (
    <span
      aria-hidden
      data-tooltip
      className="pointer-events-none absolute top-full left-1/2 z-50 mt-1.5 -translate-x-1/2 rounded-md bg-charcoal px-2 py-1 text-xs whitespace-nowrap text-ivory opacity-0 shadow-soft transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
    >
      {children}
    </span>
  );
}

export const headerIconClass =
  "group relative grid size-10 place-items-center rounded-full text-charcoal transition-colors hover:bg-sage-100";
