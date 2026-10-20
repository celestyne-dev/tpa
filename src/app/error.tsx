"use client";

import { RefreshCw } from "lucide-react";
import { useEffect } from "react";
import { Button, ButtonLink } from "@/components/ui/button";
import { Container } from "@/components/ui/container";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Hook point for future error monitoring.
    console.error(error);
  }, [error]);

  return (
    <Container size="narrow" className="py-24 text-center">
      <h1 className="text-4xl font-medium sm:text-5xl">Something went wrong</h1>
      <p className="mx-auto mt-5 max-w-lg text-lg text-muted">
        We could not load this page just now. Please try again. If the problem continues, return to
        the homepage and try again later.
      </p>
      {error.digest && <p className="mt-3 text-sm text-muted">Reference: {error.digest}</p>}
      <div className="mt-9 flex flex-col justify-center gap-3 sm:flex-row">
        <Button onClick={reset}>
          <RefreshCw aria-hidden />
          Try again
        </Button>
        <ButtonLink href="/" variant="outline">
          Back to the homepage
        </ButtonLink>
      </div>
    </Container>
  );
}
