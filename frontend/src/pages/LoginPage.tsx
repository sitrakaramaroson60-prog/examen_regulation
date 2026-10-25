import { useState, type FormEvent } from "react"
import { Navigate, useLocation, useNavigate } from "react-router"
import { SPACE_PATH, useAuth } from "../lib/auth-context"
import { describeError } from "../lib/api"
import { Eye, EyeOff, LockKeyhole, ShieldCheck } from "lucide-react"
import {
  Button,
  Card,
  Heading,
  Input,
  Text,
} from "../components/ui"

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, login } = useAuth()
  const [showPassword, setShowPassword] = useState(false)
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")
  if (user) return <Navigate to={SPACE_PATH[user.space]} replace />
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError("")
    try {
      const u = await login(email.trim(), password)
      const from = (location.state as { from?: string } | null)?.from
      navigate(from && from.startsWith(SPACE_PATH[u.space]) ? from : SPACE_PATH[u.space], { replace: true })
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoading(false)
    }
  }
  return (
    <div className="login-page">
      <div className="login-aside">
        <div className="login-brand">
          <span className="brand-mark light">
            <ShieldCheck size={28} />
          </span>
          <span>
            <strong>QoS Madagascar</strong>
            <small>Plateforme de régulation</small>
          </span>
        </div>
        <div className="login-message">
          <Text as="small">ESPACE SÉCURISÉ</Text>
          <Heading as="h1">
            Des données fiables pour une régulation éclairée.
          </Heading>
          <Text>
            Collecter, analyser et agir pour améliorer durablement la qualité
            des services de télécommunications.
          </Text>
        </div>
        <Text as="small" className="login-legal">
          Accès réservé aux organismes habilités · Les connexions sont journalisées
        </Text>
      </div>
      <div className="login-main">
        <Card className="login-card">
          <div className="login-title">
            <span className="lock-icon">
              <LockKeyhole />
            </span>
            <Heading as="h2">Connexion organisme</Heading>
            <Text>Accédez à votre espace professionnel sécurisé.</Text>
          </div>
          <form className="login-form" onSubmit={submit}>
            <Input
              label="Adresse email professionnelle"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <div className="password-field">
              <Input
                label="Mot de passe"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <Button
                type="button"
                variant="ghost"
                onClick={() => setShowPassword(!showPassword)}
                aria-label="Afficher le mot de passe"
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </Button>
            </div>
            {error && (
              <p className="field-error" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" className="full-button" loading={loading}>
              Accéder à l’espace
            </Button>
          </form>
          <div className="security-copy">
            <ShieldCheck size={18} />
            <Text as="small">
              Votre espace est déterminé par le serveur à partir de votre compte.
              Aucun rôle n’est choisi depuis cette page.
            </Text>
          </div>
        </Card>
      </div>
    </div>
  )
}
