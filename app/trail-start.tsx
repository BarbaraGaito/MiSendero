import { useEffect } from "react";
import TrailStart from "../mobile/screens/TrailStart";
import { initDB } from "../database/database";

export default function App() {

  useEffect(() => {
    initDB();
  }, []);

  return <TrailStart />;
}
