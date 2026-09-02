// app/explorar-rutas.tsx
import { useEffect } from "react";
import ExploreRoutesScreen from "../mobile/screens/ExploreRoutesScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <ExploreRoutesScreen />;
}
