import React, { useEffect } from "react";
import MapFiltersScreen from "../mobile/screens/MapFiltersScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <MapFiltersScreen />;
}