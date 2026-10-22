import { useState } from "react";
import { ButtonLink } from "@/components/ui/Button";
import { useAdminApi } from "../adminApiContext";
import { AuthCard } from "../components/AuthCard";
import { TokenPasswordForm } from "../components/TokenPasswordForm";
import { useLinkToken } from "../hooks/useLinkToken";

export function ResetPasswordPage() {
  const token = useLinkToken();
  const api = useAdminApi();
  const [done, setDone] = useState(false);
  return (
    <AuthCard title="Reset your password">
      {done ? (
        <div className="space-y-4">
          <p role="status" className="rounded-lg bg-sage-50 px-3 py-2 text-sm text-sage-800">
            Your password has been changed and other sessions were signed out.
          </p>
          <ButtonLink to="/admin/login" className="w-full">
            Sign in
          </ButtonLink>
        </div>
      ) : (
        <TokenPasswordForm
          token={token}
          verify={api.auth.verifyPasswordReset}
          submit={api.auth.completePasswordReset}
          submitLabel="Save new password"
          onDone={() => setDone(true)}
        />
      )}
    </AuthCard>
  );
}
