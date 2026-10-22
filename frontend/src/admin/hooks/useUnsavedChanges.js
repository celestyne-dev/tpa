import { useEffect } from "react";

const MESSAGE = "You have unsaved changes. Leave without saving?";

/**
 * Warns before losing unsaved work: browser reload/close, and in-app links
 * (intercepted in the capture phase before React Router handles them).
 */
export function useUnsavedChanges(dirty) {
  useEffect(() => {
    if (!dirty) return undefined;
    const beforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = MESSAGE;
    };
    const onClick = (event) => {
      const anchor = event.target.closest?.("a[href]");
      if (!anchor || anchor.target === "_blank" || anchor.dataset.allowUnsaved !== undefined)
        return;
      if (anchor.origin !== window.location.origin) return;
      if (!window.confirm(MESSAGE)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", onClick, true);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      document.removeEventListener("click", onClick, true);
    };
  }, [dirty]);
}

export { MESSAGE as UNSAVED_MESSAGE };
