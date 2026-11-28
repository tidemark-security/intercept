import { Button } from "@tidemark-security/ux";
import { useSession } from "@/contexts/sessionContext";

export function SessionCheckStatus() {
  const { status, refreshSession } = useSession();

  if (status === "unavailable") {
    return (
      <div className="flex flex-col items-center gap-3 px-6 text-center">
        <p role="alert" className="text-body font-body text-default-font">
          Intercept couldn’t check your session.
        </p>
        <Button variant="neutral-secondary" onClick={() => void refreshSession()}>
          Retry session check
        </Button>
      </div>
    );
  }

  return (
    <p role="status" className="text-body font-body text-subtext-color">
      Checking your session…
    </p>
  );
}
