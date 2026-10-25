import { useState } from "react"
import { Button, Input } from "../components/ui"
import { Notice, PageHeader, Section } from "../components/kit"
import { api, describeError, tokens } from "../lib/api"
import { useAuth } from "../lib/auth-context"

export default function Account() {
  const { user, logout } = useAuth()
  const [f, setF] = useState({ old_password: "", new_password: "", confirm: "" })
  const [msg, setMsg] = useState<{ t: "red" | "green"; m: string } | null>(null)
  const submit = async () => {
    if (f.new_password !== f.confirm) { setMsg({ t: "red", m: "La confirmation ne correspond pas au nouveau mot de passe." }); return }
    try {
      await api("/auth/change-password/", { method: "POST", body: { old_password: f.old_password, new_password: f.new_password } })
      tokens.clear()
      setMsg({ t: "green", m: "Mot de passe modifié. Vos sessions ont été fermées : reconnectez-vous." })
      window.setTimeout(() => void logout().then(() => window.location.assign("/connexion")), 1500)
    } catch (e) { setMsg({ t: "red", m: describeError(e) }) }
  }
  return (
    <div className="page-stack">
      <PageHeader title="Mon compte" subtitle="Informations de connexion et sécurité." />
      <Section title="Profil">
        <p><strong>{user?.email}</strong></p>
        <p>Organisme : {user?.organization?.name ?? "—"} · Rôle : {user?.role}</p>
        <Notice tone="blue">Votre rôle et votre organisme sont attribués par un administrateur : ils ne peuvent pas être modifiés depuis cette page.</Notice>
      </Section>
      <Section title="Changer le mot de passe" subtitle="12 caractères minimum, ni trop courant ni uniquement numérique.">
        {msg && <Notice tone={msg.t === "red" ? "red" : "green"}>{msg.m}</Notice>}
        <div className="form-stack" style={{ maxWidth: 420 }}>
          <Input label="Mot de passe actuel" type="password" autoComplete="current-password" value={f.old_password} onChange={(e) => setF({ ...f, old_password: e.target.value })} />
          <Input label="Nouveau mot de passe" type="password" autoComplete="new-password" value={f.new_password} onChange={(e) => setF({ ...f, new_password: e.target.value })} />
          <Input label="Confirmer le nouveau mot de passe" type="password" autoComplete="new-password" value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} />
          <div><Button disabled={!f.old_password || !f.new_password} onClick={submit}>Modifier le mot de passe</Button></div>
        </div>
      </Section>
    </div>
  )
}
