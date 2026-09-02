// app/reportar-terreno.tsx
import { useEffect } from "react";
import ReportTerrainScreen from "../mobile/screens/ReportTerrainScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <ReportTerrainScreen />;
}
