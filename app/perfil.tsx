// app/perfil.tsx
import { useEffect } from "react";
import ProfileScreen from "../mobile/screens/ProfileScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <ProfileScreen />;
}
