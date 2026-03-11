import { Routes, Route, Navigate } from "react-router-dom"
import { useAuth } from "./AuthContext"
import Auth from "./components/Auth"
import Home from "./components/Home"
import PdfViewer from "./components/PdfViewer"

// Dummy Components for Demonstration
// const Home = () => <div className="p-10 text-2xl">🏠 Home Page (List of PDFs)</div>
// const PdfViewer = () => <div className="p-10 text-2xl">📄 PDF Viewer</div>

function RequireAuth({ children }) {
  const { user, loading } = useAuth()

  if (loading) return <div className="flex h-screen items-center justify-center">Loading...</div>

  // If not logged in, redirect to Login page
  if (!user) {
    return <Navigate to="/login" replace />
  }

  // If logged in, render the child component
  return children
}

export default function App() {
  return (
    <Routes>
      {/* Public Route */}
      <Route path="/login" element={<Auth />} />

      {/* Protected Routes */}
      <Route
        path="/"
        element={
          <RequireAuth>
            <Home />
          </RequireAuth>
        }
      />

      <Route
        path="/document/:id"
        element={
          <RequireAuth>
            <PdfViewer />
          </RequireAuth>
        }
      />
    </Routes>
  )
}