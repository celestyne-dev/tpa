"use client";

import "./globals.css";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="grid min-h-dvh place-items-center bg-ivory p-6 text-center">
        <div className="max-w-md">
          <h1 className="font-serif text-4xl">Something went wrong</h1>
          <p className="mt-4 text-muted">
            Think Positive Always is temporarily unavailable. Please try again in a moment.
          </p>
          <button
            type="button"
            onClick={reset}
            className="mt-8 rounded-full bg-sage-700 px-6 py-3 font-medium text-ivory hover:bg-sage-800"
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
