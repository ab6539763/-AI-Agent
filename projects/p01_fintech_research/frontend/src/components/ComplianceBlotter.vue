<script setup lang="ts">
import { ref } from "vue";
import type { AuditLogEntry, ComplianceAction } from "../api/client";

defineProps<{
  pendingActions: ComplianceAction[];
  auditLogs: AuditLogEntry[];
  loading?: boolean;
}>();

const emit = defineEmits<{
  (
    e: "decide-action",
    payload: {
      action_id: string;
      decision: "approve" | "reject";
      actor_role: string;
      approver: string;
      comment: string;
    }
  ): void;
  (e: "refresh-blotter"): void;
}>();

const approver = ref("cro.wang");
const actorRole = ref("compliance_officer");
const comment = ref("Reviewed & signed off via Quant Terminal");

function formatTime(iso: string): string {
  if (!iso) return "--:--:--";
  const t = iso.split("T")[1];
  return t ? t.replace("Z", "") : iso;
}

function eventTagClass(eventType: string): string {
  if (eventType.includes("BLOCKED") || eventType.includes("REJECT")) return "tag-danger";
  if (eventType.includes("HITL") || eventType.includes("APPROV")) return "tag-amber";
  if (eventType.includes("QUANT") || eventType.includes("STREAM")) return "tag-cyan";
  return "tag-muted";
}

function summarizeAudit(log: AuditLogEntry): string {
  const parts: string[] = [];
  if (log.issuer_id) parts.push(`issuer=${String(log.issuer_id)}`);
  if (log.credit_rating) parts.push(`rtg=${String(log.credit_rating)}`);
  if (log.composite_score !== undefined) parts.push(`scr=${String(log.composite_score)}`);
  if (log.decision) parts.push(`dec=${String(log.decision)}`);
  if (log.approver) parts.push(`by=${String(log.approver)}`);
  if (log.doc_id) parts.push(`doc=${String(log.doc_id)}`);
  if (log.screened_count !== undefined) parts.push(`n=${String(log.screened_count)}`);
  return parts.join(" · ") || log.event_id.slice(0, 8);
}
</script>

<template>
  <aside class="terminal-panel blotter-panel">
    <div class="panel-header">
      <div class="panel-title-group">
        <span class="panel-dot"></span>
        <h2>COMPLIANCE BLOTTER</h2>
      </div>
      <button class="btn-mini" :disabled="loading" @click="emit('refresh-blotter')">
        REFRESH
      </button>
    </div>

    <!-- HITL Sign-Off Controls -->
    <div class="blotter-section">
      <div class="section-label">
        <span>HITL SIGN-OFF QUEUE</span>
        <span class="count-pill" :class="{ alert: pendingActions.length > 0 }">
          {{ pendingActions.length }}
        </span>
      </div>

      <div class="signoff-form">
        <div class="signoff-row">
          <input
            v-model="approver"
            type="text"
            class="terminal-input"
            placeholder="Approver ID"
          />
          <select v-model="actorRole" class="terminal-input">
            <option value="compliance_officer">compliance_officer</option>
            <option value="risk_committee">risk_committee</option>
            <option value="cro">cro</option>
            <option value="analyst">analyst</option>
          </select>
        </div>
        <input
          v-model="comment"
          type="text"
          class="terminal-input"
          placeholder="Sign-off rationale..."
        />
      </div>

      <div class="hitl-list">
        <div v-for="act in pendingActions" :key="act.action_id" class="hitl-card">
          <div class="hitl-card-top">
            <span class="hitl-type">{{ act.action_type }}</span>
            <span class="sev-pill" :class="`sev-${act.min_severity.toLowerCase()}`">
              {{ act.min_severity }}
            </span>
          </div>
          <div class="hitl-meta">
            <span>ISSUER: <strong>{{ act.issuer_id }}</strong></span>
            <span>REQ ROLE: <strong>{{ act.required_role }}</strong></span>
          </div>
          <p class="hitl-rationale">{{ act.rationale }}</p>
          <div class="hitl-actions">
            <button
              class="btn-approve"
              :disabled="loading"
              @click="
                emit('decide-action', {
                  action_id: act.action_id,
                  decision: 'approve',
                  actor_role: actorRole,
                  approver,
                  comment,
                })
              "
            >
              APPROVE
            </button>
            <button
              class="btn-reject"
              :disabled="loading"
              @click="
                emit('decide-action', {
                  action_id: act.action_id,
                  decision: 'reject',
                  actor_role: actorRole,
                  approver,
                  comment,
                })
              "
            >
              REJECT
            </button>
          </div>
        </div>

        <div v-if="pendingActions.length === 0" class="empty-state">
          No pending HITL compliance escalations.
        </div>
      </div>
    </div>

    <!-- Immutable Audit Stream -->
    <div class="blotter-section audit-section">
      <div class="section-label">
        <span>AUDIT TRAIL STREAM</span>
        <span class="count-pill">{{ auditLogs.length }}</span>
      </div>

      <div class="audit-stream">
        <div v-for="log in auditLogs" :key="log.event_id" class="audit-row">
          <div class="audit-row-top">
            <span class="audit-tag" :class="eventTagClass(log.event_type)">
              {{ log.event_type }}
            </span>
            <span class="audit-time">{{ formatTime(log.timestamp) }}</span>
          </div>
          <div class="audit-detail">{{ summarizeAudit(log) }}</div>
        </div>

        <div v-if="auditLogs.length === 0" class="empty-state">
          Awaiting audit events...
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.blotter-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.blotter-section {
  display: flex;
  flex-direction: column;
  padding: 10px 12px;
  border-bottom: 1px solid #1e293b;
}

.audit-section {
  flex: 1;
  min-height: 0;
  border-bottom: none;
}

.section-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #94a3b8;
  margin-bottom: 8px;
}

.count-pill.alert {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
  border-color: rgba(239, 68, 68, 0.45);
}

.signoff-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
}

.signoff-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

.hitl-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 250px;
  overflow-y: auto;
}

.hitl-card {
  background: #0d1320;
  border: 1px solid #263147;
  border-left: 3px solid #f59e0b;
  border-radius: 4px;
  padding: 9px;
}

.hitl-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.hitl-type {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  font-weight: 700;
  color: #f59e0b;
}

.sev-pill {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
}

.sev-critical {
  background: rgba(239, 68, 68, 0.2);
  color: #f87171;
}

.sev-high {
  background: rgba(245, 158, 11, 0.2);
  color: #fbbf24;
}

.sev-medium,
.sev-low {
  background: rgba(56, 189, 248, 0.15);
  color: #38bdf8;
}

.hitl-meta {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: #94a3b8;
  margin-top: 4px;
}

.hitl-meta strong {
  color: #e2e8f0;
}

.hitl-rationale {
  font-size: 11px;
  color: #cbd5e1;
  margin: 6px 0 8px;
  line-height: 1.4;
}

.hitl-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}

.btn-approve,
.btn-reject {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  font-weight: 700;
  padding: 5px 8px;
  border-radius: 3px;
  cursor: pointer;
  border: 1px solid transparent;
}

.btn-approve {
  background: rgba(16, 185, 129, 0.16);
  color: #34d399;
  border-color: rgba(16, 185, 129, 0.4);
}

.btn-approve:hover:not(:disabled) {
  background: rgba(16, 185, 129, 0.28);
}

.btn-reject {
  background: rgba(239, 68, 68, 0.16);
  color: #f87171;
  border-color: rgba(239, 68, 68, 0.4);
}

.btn-reject:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.28);
}

.audit-stream {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.audit-row {
  background: #070b12;
  border: 1px solid #162033;
  border-radius: 4px;
  padding: 7px 9px;
}

.audit-row-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.audit-tag {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
}

.tag-danger {
  background: rgba(239, 68, 68, 0.18);
  color: #f87171;
}

.tag-amber {
  background: rgba(245, 158, 11, 0.18);
  color: #fbbf24;
}

.tag-cyan {
  background: rgba(56, 189, 248, 0.16);
  color: #38bdf8;
}

.tag-muted {
  background: #1e293b;
  color: #94a3b8;
}

.audit-time {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: #64748b;
}

.audit-detail {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: #94a3b8;
  margin-top: 4px;
  word-break: break-word;
}
</style>
