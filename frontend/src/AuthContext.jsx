import { createContext, useState, useEffect, useContext } from "react"
const AuthContext = createContext(null)

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        async function checkUser() {
            try {
                const response = await fetch("http://localhost:3000/api/auth/me", {
                    method: "GET",
                    credentials: "include"  // 'include' tells fetch to bring the cookie along
                })

                if (response.ok) { // Status is 200-299
                    const data = await response.json()
                    setUser(data)
                }
            } catch (error) {
                console.error("Not logged in")
            } finally {
                setLoading(false)
            }
        }

        checkUser()
    }, [])

    const login = async (email, password) => {
        const response = await fetch("http://localhost:3000/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
            credentials: "include", 
        })

        if (!response.ok) {
            const err = await response.json()
            throw new Error(err.message || "Login failed")
        }

        const data = await response.json()
        setUser({ 
            email: data.email 
        }) 
    }

    const logout = async () => {
        await fetch("http://localhost:3000/api/auth/logout", {
            method: "POST",
            credentials: "include"
        })
        setUser(null) // Clear local state immediately
    }

    const register = async (email, password) => {
        const response = await fetch("http://localhost:3000/api/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
            credentials: "include", 
        })

        if (!response.ok) {
            const err = await response.json()
            throw new Error(err.message || "Sign Up failed")
        }

        const data = await response.json()
        setUser({ 
            email: data.email 
        }) 
    }

    const value = {
        user,
        loading,
        login,
        logout,
        register
    }

    return (
        <AuthContext.Provider value={value}>
            {!loading && children} 
        </AuthContext.Provider>
    )
}

export const useAuth = () => useContext(AuthContext)