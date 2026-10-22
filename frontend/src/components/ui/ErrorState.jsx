import { CloudOff, RefreshCw } from "lucide-react";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";

/** Graceful fallback when the API is unreachable or returns an error. */
export function ErrorState({
  title = "We couldn't load this content",
  message = "Please check your connection and try again in a moment.",
  onRetry,
  className,
}) {
  return (
    <div role="alert">
      <EmptyState
        icon={CloudOff}
        title={title}
        description={message}
        className={className}
        action={
          onRetry && (
            <Button onClick={onRetry} variant="outline">
              <RefreshCw aria-hidden />
              Try again
            </Button>
          )
        }
      />
    </div>
  );
}
