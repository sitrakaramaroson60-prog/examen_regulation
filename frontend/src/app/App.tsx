import { useEffect } from "react"
import { RouterProvider } from "react-router"
import { AuthProvider } from "../lib/AuthProvider"
import { realtime } from "../lib/realtime"
import { router } from "./routes"

export default function App() {
  useEffect(() => {
    realtime.start() // connexion temps réel pour toute l'application (public et espaces professionnels)
    return () => realtime.stop()
  }, [])
  return (
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  )
}
