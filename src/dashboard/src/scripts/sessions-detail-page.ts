import {
  getSessionDetail,
  deleteSession,
} from "../lib/api/admin";
import { showDangerConfirm } from "./modal-controller";

const titleEl = document.querySelector("#detail-title");
const sessionIdVal = document.querySelector("#session-id-val");
const userIdVal = document.querySelector("#session-user-id");
const clientIdVal = document.querySelector("#session-client-id");
const createdAtVal = document.querySelector("#session-created-at");
const lastActiveVal = document.querySelector("#session-last-active");

const projectContextVal = document.querySelector("#project-context-val");
const activeSkillsVal = document.querySelector("#active-skills-val");
const stateVal = document.querySelector("#session-state-val");

const deleteBtn = document.querySelector("#delete-session");

const sessionId = window.location.pathname.split("/").pop() || "";

async function refreshDetail() {
  if (!sessionId) return;
  
  try {
    const { session } = await getSessionDetail(sessionId);
    
    if (titleEl) titleEl.textContent = session.name || session.id.slice(0, 8);
    if (sessionIdVal) sessionIdVal.textContent = session.id;
    if (userIdVal) userIdVal.textContent = session.user_id || "Anonymous";
    if (clientIdVal) clientIdVal.textContent = session.client_id || "Direct";
    if (createdAtVal) createdAtVal.textContent = session.created_at ? new Date(session.created_at).toLocaleString() : "n/a";
    if (lastActiveVal) lastActiveVal.textContent = session.last_active ? new Date(session.last_active).toLocaleString() : "n/a";
    
    if (projectContextVal) projectContextVal.textContent = JSON.stringify(session.project_context, null, 2);
    if (activeSkillsVal) activeSkillsVal.textContent = JSON.stringify(session.active_skills, null, 2);
    if (stateVal) stateVal.textContent = JSON.stringify(session.state, null, 2);
    
  } catch (err) {
    console.error("Failed to load session detail:", err);
    if (titleEl) titleEl.textContent = "Error loading session";
  }
}

deleteBtn?.addEventListener("click", async () => {
  const confirmed = await showDangerConfirm(
    "Are you sure you want to delete this session? This will clear all runtime memory associated with it."
  );
  
  if (confirmed && sessionId) {
    try {
      await deleteSession(sessionId);
      window.location.href = "/dashboard/sessions";
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to delete session");
    }
  }
});

void refreshDetail();
