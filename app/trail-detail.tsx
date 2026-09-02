import { useEffect } from "react";
import TrailDetail from "../mobile/screens/TrailDetail";
import { initDB } from "../database/database";

export default function App() {

  useEffect(() => {
    initDB();
  }, []);

  return <TrailDetail />;
}
