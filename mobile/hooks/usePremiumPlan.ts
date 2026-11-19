import { useEffect, useState } from "react";
import { getAuthSession } from "../../services/authSession";

// The topographic and satellite layers are billed per tile (Esri), so only
// premium accounts can open them; free accounts use the base map.
export function usePremiumPlan() {
  const [premium, setPremium] = useState(false);
  useEffect(() => {
    let active = true;
    void getAuthSession()
      .then((session) => { if (active) setPremium(session?.user.plan === "premium"); })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);
  return premium;
}
