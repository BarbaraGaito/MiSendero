// app/reporte-guardado.tsx
import { useEffect } from "react";
import ReportSavedScreen from "../mobile/screens/ReportSavedScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <ReportSavedScreen />;
}
