"use client";

import {useCallback, useEffect, useState} from "react";
import {api} from "@/lib/api";

type Role = "user" | "admin" | "super_admin";
type Member = {id:string; name:string; email:string; role:string};
type MemberPage = {items:Member[];total:number};
const PAGE_SIZE = 50;

export default function AdminTeam({currentUserId}:{currentUserId:string}) {
  const [page,setPage] = useState(0);
  const [result,setResult] = useState<MemberPage|null>(null);
  const [loading,setLoading] = useState(true);
  const [saving,setSaving] = useState("");
  const [error,setError] = useState("");
  const [notice,setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);setError("");
    try {
      setResult(await api<MemberPage>(`/admin/team?limit=${PAGE_SIZE}&offset=${page*PAGE_SIZE}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load team.");
    } finally {setLoading(false);}
  },[page]);
  useEffect(()=>{void load();},[load]);

  async function updateRole(member:Member,role:Role) {
    if (member.id===currentUserId || role===member.role) return;
    if (!window.confirm(`Change ${member.email} from ${member.role} to ${role}?`)) return;
    setSaving(member.id);setError("");setNotice("");
    try {
      await api<Member>(`/admin/team/${encodeURIComponent(member.id)}/role`,"PATCH",{role});
      setNotice("Role updated. The affected user should sign in again to refresh their session.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change role.");
    } finally {setSaving("");}
  }

  return <section className="admin-section">
    <div className="admin-section-heading">
      <div><p className="admin-overline">ACCESS CONTROL</p><h1>Team & roles</h1>
      <p>Only super administrators can change roles. All accounts are users by default.</p></div>
    </div>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {loading ? <p role="status">Loading team…</p> : result && <>
      <div style={{overflowX:"auto"}}>
        <table style={{width:"100%",textAlign:"left",borderCollapse:"collapse"}}>
          <thead><tr><th style={{padding:"12px"}}>Name</th><th style={{padding:"12px"}}>Email</th><th style={{padding:"12px"}}>Role</th></tr></thead>
          <tbody>{result.items.map(member=><tr key={member.id}>
            <td style={{padding:"12px"}}>{member.name}</td>
            <td style={{padding:"12px"}}>{member.email}</td>
            <td style={{padding:"12px"}}>
              <select aria-label={`Role for ${member.email}`} value={member.role}
                disabled={saving!=="" || member.id===currentUserId}
                onChange={event=>void updateRole(member,event.target.value as Role)}>
                <option value="user">User</option>
                <option value="admin">Admin</option>
                <option value="super_admin">Super admin</option>
              </select>
              {member.id===currentUserId ? " (you)" : ""}
            </td></tr>)}</tbody>
        </table>
      </div>
      <p>{result.total} registered accounts · showing {result.items.length} on this page</p>
      <div style={{display:"flex",gap:"12px",marginTop:"12px"}}>
        <button disabled={page===0 || loading} onClick={()=>setPage(p=>Math.max(0,p-1))}>Previous</button>
        <button disabled={(page+1)*PAGE_SIZE>=result.total || loading} onClick={()=>setPage(p=>p+1)}>Next</button>
      </div>
    </>}
  </section>;
}
