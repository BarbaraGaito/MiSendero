// app/confirmar-sos.tsx
import React, { useEffect } from "react";
import ConfirmSosScreen from "../mobile/screens/ConfirmSosScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <ConfirmSosScreen />;
}