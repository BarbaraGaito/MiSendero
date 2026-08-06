import React, { useEffect } from "react";
import RouteMap from "../mobile/screens/RouteMap";
import { initDB } from "../database/database";

export default function App() {

  useEffect(() => {
    initDB();
  }, []);

  return <RouteMap />;
}