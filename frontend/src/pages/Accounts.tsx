import { useState } from "react"
import { Badge, Button, Input, Select } from "../components/ui"
import { Empty, ErrorMsg, Loading, Notice, PageHeader, Section, Table } from "../components/kit"
import { fmtDate } from "../lib/format"
import { api, describeError, type Page } from "../lib/api"
import { useAuth } from "../lib/auth-context"
import { useFetch } from "../lib/useFetch"

type UserRow = { id: number; email: string; first_name: string; last_name: string; organization: string | null; role: string; is_active: boolean; last_login: string | null }
const ROLES: Record<string, string> = { OPERATOR_USER: "Opérateur", ARTEC_PUBLISHER: "ARTEC — Publications", ARTEC_REGULATOR: "ARTEC — Régulation et prédiction", SYSTEM_ADMIN: "Administrateur système" }

/** Gestion des comptes et des accès. ARTEC Régulation : comptes d'opérateurs ; administrateur système : tous les comptes. */
export default function Accounts() {
  const { user } = useAuth()
  const admin = user?.role === "SYSTEM_ADMIN"
  const [search, setSearch] = useState("")
  const list = useFetch<Page<UserRow>>("/auth/users/", { search, page_size: 100 })
  const orgs = useFetch<{ code: string; organization_type: string }[]>("/organizations/")
  const [f, setF] = useState({ email: "", first_name: "", last_name: "", role: "OPERATOR_USER", organization: "", password: "" })
  const [msg, setMsg] = useState<{ t: "red" | "green"; m: string } | null>(null)
  const roles = admin ? Object.keys(ROLES) : ["OPERATOR_USER"]
  const orgOptions = (orgs.data ?? []).filter((o) => (f.role === "OPERATOR_USER" ? o.organization_type === "OPERATOR" : o.code === "ARTEC"))

  const create = async () => {
    try {
      await api("/auth/users/", { method: "POST", body: { ...f, organization: f.organization || null } })
      setMsg({ t: "green", m: "Compte créé. Transmettez le mot de passe initial par un canal sûr et demandez son changement dès la première connexion." })
      setF({ ...f, email: "", first_name: "", last_name: "", password: "" })
      list.reload()
    } catch (e) { setMsg({ t: "red", m: describeError(e) }) }
  }
  const patch = async (u: UserRow, body: Record<string, unknown>, ok: string) => {
    try { await api(`/auth/users/${u.id}/`, { method: "PATCH", body }); setMsg({ t: "green", m: ok }); list.reload() } catch (e) { setMsg({ t: "red", m: describeError(e) }) }
  }

  return (
    <div className="page-stack">
      <PageHeader title="Comptes et accès" subtitle={admin ? "Tous les comptes des organismes." : "Comptes des opérateurs YAS, AIRTEL et ORANGE. Les comptes ARTEC sont gérés par l'administrateur système."} />
      {msg && <Notice tone={msg.t === "red" ? "red" : "green"}>{msg.m}</Notice>}
      <Section title="Comptes existants">
        <Input placeholder="Rechercher par email ou nom…" value={search} onChange={(e) => setSearch(e.target.value)} />
        {list.loading && <Loading />}
        {list.error && <ErrorMsg>{list.error}</ErrorMsg>}
        {list.data && list.data.results.length === 0 && <Empty>Aucun compte.</Empty>}
        {list.data && list.data.results.length > 0 && (
          <Table head={["Email", "Organisme", "Rôle", "Dernière connexion", "État", ""]}>
            {list.data.results.map((u) => (
              <tr key={u.id}>
                <td><strong>{u.email}</strong><div className="ind-meta">{`${u.first_name} ${u.last_name}`.trim()}</div></td><td>{u.organization ?? "—"}</td><td>{ROLES[u.role] ?? u.role}</td>
                <td>{fmtDate(u.last_login)}</td><td>{u.is_active ? <Badge tone="green">Actif</Badge> : <Badge tone="gray">Désactivé</Badge>}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <Button size="sm" variant="secondary" disabled={u.id === user?.id} onClick={() => patch(u, { is_active: !u.is_active }, u.is_active ? "Compte désactivé." : "Compte réactivé.")}>{u.is_active ? "Désactiver" : "Réactiver"}</Button>{" "}
                  <Button size="sm" variant="ghost" onClick={() => { const p = window.prompt("Nouveau mot de passe (12 caractères minimum) :"); if (p) patch(u, { password: p }, "Mot de passe réinitialisé.") }}>Réinitialiser le mot de passe</Button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Section>
      <Section title="Créer un compte" subtitle="L'inscription publique n'existe pas : tout compte professionnel est créé par une personne habilitée.">
        <div className="form-stack">
          <div className="form-row">
            <Input label="Adresse email" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
            <Input label="Prénom" value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} />
            <Input label="Nom" value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} />
          </div>
          <div className="form-row">
            <Select label="Rôle" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value, organization: "" })} disabled={!admin}>{roles.map((r) => <option key={r} value={r}>{ROLES[r]}</option>)}</Select>
            <Select label="Organisme" value={f.organization} onChange={(e) => setF({ ...f, organization: e.target.value })}><option value="">Sélectionner…</option>{orgOptions.map((o) => <option key={o.code}>{o.code}</option>)}</Select>
            <Input label="Mot de passe initial" type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          </div>
          <div><Button disabled={!f.email || !f.password || (f.role !== "SYSTEM_ADMIN" && !f.organization)} onClick={create}>Créer le compte</Button></div>
        </div>
      </Section>
    </div>
  )
}
