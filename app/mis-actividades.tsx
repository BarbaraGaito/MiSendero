// app/mis-actividades.tsx
import { useEffect } from "react";
import ActivitiesScreen from "../mobile/screens/ActivitiesScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <ActivitiesScreen />;
}
