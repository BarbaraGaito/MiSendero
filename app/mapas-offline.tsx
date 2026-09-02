// app/mapas-offline.tsx
import { useEffect } from "react";
import OfflineMapsScreen from "../mobile/screens/OfflineMapsScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <OfflineMapsScreen />;
}
