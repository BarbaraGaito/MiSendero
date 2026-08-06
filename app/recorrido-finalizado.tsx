// app/recorrido-finalizado.tsx
import React, { useEffect } from "react";
import RouteCompletedScreen from "../mobile/screens/RouteCompletedScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <RouteCompletedScreen />;
}