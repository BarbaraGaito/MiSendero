// app/descanso.tsx
import { useEffect } from "react";
import RestBreakScreen from "../mobile/screens/RestBreakScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <RestBreakScreen />;
}
