import { useState } from "react"
import { useAuth } from '../AuthContext'
import { useNavigate } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Lock } from "lucide-react"

export default function Login() {
  const { login, register } = useAuth()
  const navigate = useNavigate()
  
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  
  const [formType, setFormType] = useState("signIn") // Options: signIn | signUp

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError("") 
    
    try {
      if (formType === "signUp") {
        await register(email, password)
      } else {
        await login(email, password)
      }
      navigate("/")
    } catch (err) {
      setError(err.message || "Authentication failed")
    }
  }

  // Helper to flip the form and clear out old errors
  const toggleForm = () => {
    setFormType(prev => prev === "signIn" ? "signUp" : "signIn")
    setError("") 
  }

  return (
    <div className="min-h-screen flex flex-col bg-background">
      
      <header className="flex items-center justify-between border-b px-6 py-3 bg-background">
        <div className="flex items-center gap-3">
          <div className="h-6 w-6 text-primary">
            <div className="h-6 w-6 rounded-full bg-primary" />
          </div>
          <span className="text-lg font-bold tracking-tight">
            LegalDoc AI
          </span>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-6">
        <Card className="w-full max-w-[440px] rounded-xl shadow-lg">
          
          <CardHeader className="space-y-2 text-center">
            <h1 className="text-2xl font-bold tracking-tight">
              {formType === "signIn" ? "Sign in to your account" : "Create a new account"}
            </h1>
            <p className="text-sm text-muted-foreground">
              {formType === "signIn" 
                ? "Access your secure legal workspace" 
                : "Start analyzing legal documents securely"}
            </p>
          </CardHeader>

          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-5">
              
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="name@company.com"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required 
                />
              </div>

              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <Label htmlFor="password">Password</Label>
                  {formType === "signIn" && (
                    <button type="button" className="text-xs text-primary hover:underline">
                      Forgot password?
                    </button>
                  )}
                </div>
                <Input
                  id="password"
                  type="password"
                  placeholder={formType === "signIn" ? "Enter your password" : "Create a strong password"}
                  autoComplete={formType === "signIn" ? "current-password" : "new-password"}
                  value={password} 
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>

              {error && <p className="text-sm text-red-500">{error}</p>}

              <Button type="submit" className="w-full h-12 text-base font-semibold">
                {formType === "signIn" ? "Sign In" : "Create Account"}
              </Button>
            </form>
          </CardContent>

          <CardFooter className="flex flex-col gap-4 border-t pt-6">
            {/* The Toggle Switch */}
            <div className="text-sm text-center">
              {formType === "signIn" ? "Don't have an account? " : "Already have an account? "}
              <button 
                type="button" 
                onClick={toggleForm}
                className="text-primary font-semibold hover:underline"
              >
                {formType === "signIn" ? "Sign up" : "Sign in"}
              </button>
            </div>

            <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
              <Lock className="h-4 w-4" />
              <span className="font-medium">
                Privacy-first. Documents processed securely.
              </span>
            </div>
          </CardFooter>

        </Card>
      </main>

      <footer className="py-8 px-6 text-center text-xs text-muted-foreground">
        <p className="mt-4 text-[10px] uppercase tracking-widest">
          2026 LegalDoc AI. Made with ❤️ by Gourav.
        </p>
      </footer>

    </div>
  )
}