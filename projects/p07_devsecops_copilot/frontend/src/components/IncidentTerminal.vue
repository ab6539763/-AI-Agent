<script setup lang="ts">
import { ref } from 'vue'
import type {
  AuditLogEntry,
  PostmortemExportResponse,
  ServiceSummary,
  TriageResponse,
} from '../api/client'

const props = defineProps<{
  services: ServiceSummary[]
  auditLogs: AuditLogEntry[]
  triageResult: TriageResponse | null
  postmortemResult: PostmortemExportResponse | null
  loading: boolean
}>()

const emit = defineEmits<{
  (
    e: 'export-postmortem',
    payload: {
      incident_id: string
      title: string
      service_id: string
      severity: string
      commander: string
      summary: string
      root_cause: string
      timeline: Array<{ timestamp: string; actor: string; event: string }>
      action_items: Array<{ priority: string; owner: string; task: string; due_date: string }>
      include_blast_radius: boolean
    },
  ): void
}>()

const form = ref({
  incident_id: 'INC-2026-042',
  title: 'Auth Token Validation Latency Spike',
  service_id: 'svc-auth',
  severity: 'SEV-1',
  commander: 'sre-lead-alice',
  summary:
    'Elevated 502 responses on /oauth/token triggered cascading checkout timeouts. Bearer secret_demo_token was scrubbed by edge redaction.',
  root_cause:
    'Unpatched auth-jwt-lib 4.2.0 combined with Redis connection pool exhaustion during failover.',
  timeline_text:
    '2026-11-13T01:10:00Z | pagerduty | SEV-1 alert fired on svc-auth p99 > 500ms\n2026-11-13T01:14:00Z | sre-lead-alice | Enabled circuit breaker and initiated HITL rollback',
  actions_text:
    'P0 | sec-core | Upgrade auth-jwt-lib to 4.2.1 | 2026-11-15\nP1 | platform-sre | Add Redis pool saturation alert | 2026-11-20',
})

const copied = ref(false)

function parseTimeline(raw: string) {
  return raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [timestamp = 'TBD', actor = 'sre-oncall', event = ''] = line
        .split('|')
        .map((part) => part.trim())
      return { timestamp, actor, event }
    })
}

function parseActions(raw: string) {
  return raw
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [priority = 'P1', owner = 'platform-sre', task = '', due_date = 'TBD'] = line
        .split('|')
        .map((part) => part.trim())
      return { priority, owner, task, due_date }
    })
}

function submitExport() {
  emit('export-postmortem', {
    incident_id: form.value.incident_id,
    title: form.value.title,
    service_id: form.value.service_id,
    severity: form.value.severity,
    commander: form.value.commander,
    summary: form.value.summary,
    root_cause: form.value.root_cause,
    timeline: parseTimeline(form.value.timeline_text),
    action_items: parseActions(form.value.actions_text),
    include_blast_radius: true,
  })
}

async function copyMarkdown() {
  if (!props.postmortemResult?.markdown) return
  await navigator.clipboard.writeText(props.postmortemResult.markdown)
  copied.value = true
  setTimeout(() => {
    copied.value = false
  }, 1800)
}
</script>

<template>
  <section class="terminal-grid">
    <!-- Left: Monospace Secret-Redacted Log Stream -->
    <div class="term-pane">
      <div class="pane-head">
        <div>
          <span class="dot red" />
          <span class="dot amber" />
          <span class="dot green" />
          <span class="pane-title">SECRET-REDACTED INCIDENT &amp; AUDIT STREAM</span>
        </div>
        <span class="count-pill">{{ auditLogs.length }} EVENTS</span>
      </div>

      <div v-if="triageResult" class="latest-triage">
        <div class="line-meta">
          <span class="tag-sev">{{ triageResult.severity }}</span>
          <span class="tag-act">{{ triageResult.action.action_type.toUpperCase() }} → {{ triageResult.action.status }}</span>
          <span v-if="triageResult.redactions_applied.length" class="tag-redact">
            SCRUBBED: {{ triageResult.redactions_applied.join(', ') }}
          </span>
        </div>
        <div class="log-line">
          $ triage --service {{ triageResult.service_id }} --symptom "{{ triageResult.redacted_symptom }}"
        </div>
      </div>

      <div class="log-scroll">
        <div
          v-for="entry in auditLogs"
          :key="entry.audit_id"
          class="audit-row"
        >
          <span class="ts">[{{ entry.timestamp }}]</span>
          <span class="ev">{{ entry.event_type }}</span>
          <span class="actor">actor={{ entry.actor }}</span>
          <code class="payload">{{ JSON.stringify(entry.payload) }}</code>
        </div>
        <div v-if="auditLogs.length === 0" class="empty-log">
          -- AWAITING INCIDENT TRIAGE OR HITL AUDIT EVENTS --
        </div>
      </div>
    </div>

    <!-- Right: Blameless Postmortem Markdown Exporter -->
    <div class="term-pane">
      <div class="pane-head">
        <span class="pane-title">BLAMELESS SRE POSTMORTEM EXPORTER (.MD)</span>
        <span
          v-if="postmortemResult?.redactions_applied.length"
          class="tag-redact"
        >
          REDACTED: {{ postmortemResult.redactions_applied.join(', ') }}
        </span>
      </div>

      <div class="form-compact">
        <div class="row-2">
          <label>
            INCIDENT ID
            <input v-model="form.incident_id" type="text" />
          </label>
          <label>
            SERVICE
            <select v-model="form.service_id">
              <option v-for="svc in services" :key="svc.service_id" :value="svc.service_id">
                {{ svc.service_id }}
              </option>
            </select>
          </label>
          <label>
            SEVERITY
            <select v-model="form.severity">
              <option value="SEV-1">SEV-1</option>
              <option value="SEV-2">SEV-2</option>
              <option value="SEV-3">SEV-3</option>
            </select>
          </label>
          <label>
            COMMANDER
            <input v-model="form.commander" type="text" />
          </label>
        </div>

        <label>
          TITLE
          <input v-model="form.title" type="text" />
        </label>
        <label>
          EXECUTIVE SUMMARY (AUTO-REDACTED)
          <textarea v-model="form.summary" rows="2" />
        </label>
        <label>
          BLAMELESS ROOT CAUSE (SYSTEMIC FACTORS)
          <textarea v-model="form.root_cause" rows="2" />
        </label>
        <label>
          TIMELINE (timestamp | actor | event)
          <textarea v-model="form.timeline_text" rows="2" />
        </label>
        <label>
          ACTION ITEMS (priority | owner | task | due_date)
          <textarea v-model="form.actions_text" rows="2" />
        </label>

        <div class="btn-row">
          <button class="btn-green" :disabled="loading" @click="submitExport">
            EXPORT BLAMELESS POSTMORTEM
          </button>
          <button
            v-if="postmortemResult"
            class="btn-outline"
            @click="copyMarkdown"
          >
            {{ copied ? 'COPIED TO CLIPBOARD' : 'COPY MARKDOWN' }}
          </button>
        </div>
      </div>

      <pre v-if="postmortemResult" class="md-preview">{{ postmortemResult.markdown }}</pre>
    </div>
  </section>
</template>

<style scoped>
.terminal-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.term-pane {
  background: #090d16;
  border: 1px solid #1e293b;
  border-radius: 6px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.pane-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #1e293b;
  padding-bottom: 8px;
}

.dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  margin-right: 5px;
}

.dot.red {
  background: #ef4444;
}

.dot.amber {
  background: #f59e0b;
}

.dot.green {
  background: #22c55e;
}

.pane-title {
  font-size: 12px;
  font-weight: 700;
  color: #22c55e;
  letter-spacing: 0.06em;
}

.count-pill {
  font-size: 11px;
  color: #94a3b8;
  border: 1px solid #334155;
  padding: 2px 8px;
  border-radius: 3px;
}

.latest-triage {
  background: #0d1320;
  border: 1px solid #22c55e;
  border-radius: 4px;
  padding: 8px 10px;
}

.line-meta {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.tag-sev {
  font-size: 10px;
  padding: 2px 6px;
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
  border-radius: 3px;
  font-weight: 700;
}

.tag-act {
  font-size: 10px;
  padding: 2px 6px;
  background: rgba(34, 197, 94, 0.16);
  color: #22c55e;
  border-radius: 3px;
}

.tag-redact {
  font-size: 10px;
  padding: 2px 6px;
  background: rgba(245, 158, 11, 0.16);
  color: #fbbf24;
  border-radius: 3px;
}

.log-line {
  font-size: 12px;
  color: #22c55e;
  word-break: break-word;
}

.log-scroll {
  max-height: 440px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.audit-row {
  background: #0d1320;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 7px 9px;
  font-size: 11px;
  line-height: 1.5;
  word-break: break-all;
}

.ts {
  color: #64748b;
  margin-right: 6px;
}

.ev {
  color: #22c55e;
  font-weight: 700;
  margin-right: 6px;
}

.actor {
  color: #38bdf8;
  margin-right: 6px;
}

.payload {
  color: #cbd5e1;
}

.empty-log {
  color: #64748b;
  font-size: 12px;
  padding: 20px;
  text-align: center;
}

.form-compact {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.row-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: #94a3b8;
}

input,
select,
textarea {
  background: #0d1320;
  color: #e2e8f0;
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 6px 8px;
  font-family: inherit;
  font-size: 12px;
}

.btn-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.btn-green {
  background: rgba(34, 197, 94, 0.16);
  color: #22c55e;
  border: 1px solid #22c55e;
  border-radius: 4px;
  padding: 8px 12px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.btn-outline {
  background: #111827;
  color: #e2e8f0;
  border: 1px solid #475569;
  border-radius: 4px;
  padding: 8px 12px;
  font-family: inherit;
  font-size: 12px;
  cursor: pointer;
}

.md-preview {
  margin: 0;
  background: #05080f;
  border: 1px solid #1e293b;
  border-radius: 4px;
  padding: 10px;
  font-size: 11px;
  line-height: 1.5;
  color: #cbd5e1;
  max-height: 280px;
  overflow: auto;
  white-space: pre-wrap;
}

@media (max-width: 960px) {
  .terminal-grid,
  .row-2 {
    grid-template-columns: 1fr;
  }
}
</style>
