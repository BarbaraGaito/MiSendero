// app/contacto-seguridad.tsx
import { useEffect } from "react";
import SafetyContactScreen from "../mobile/screens/SafetyContactScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <SafetyContactScreen />;
}
