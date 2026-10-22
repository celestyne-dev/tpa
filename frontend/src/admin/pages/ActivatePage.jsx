import { useDispatch } from "react-redux";
import { useNavigate } from "react-router";
import { signedIn } from "@/store/slices/authSlice";
import { useAdminApi } from "../adminApiContext";
import { AuthCard } from "../components/AuthCard";
import { TokenPasswordForm } from "../components/TokenPasswordForm";
import { useLinkToken } from "../hooks/useLinkToken";

export function ActivatePage() {
  const token = useLinkToken();
  const api = useAdminApi();
  const dispatch = useDispatch();
  const navigate = useNavigate();
  return (
    <AuthCard
      title="Activate your account"
      subtitle="Choose your own password to finish setting up access."
    >
      <TokenPasswordForm
        token={token}
        askName
        verify={api.auth.verifyInvitation}
        submit={api.auth.acceptInvitation}
        submitLabel="Activate account"
        onDone={(res) => {
          dispatch(signedIn(res.data.user));
          navigate("/admin", { replace: true });
        }}
      />
    </AuthCard>
  );
}
