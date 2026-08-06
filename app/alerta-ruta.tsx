// app/alerta-ruta.tsx
import React, { useEffect } from "react";
import AlertRouteScreen from "../mobile/screens/AlertRouteScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <AlertRouteScreen />;
}