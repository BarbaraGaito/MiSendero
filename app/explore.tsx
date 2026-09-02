import { useEffect } from "react";
import Explore from "../mobile/screens/Explore";
import { initDB } from "../database/database";

export default function App() {

  useEffect(() => {
    initDB();
  }, []);

  return <Explore />;
}
