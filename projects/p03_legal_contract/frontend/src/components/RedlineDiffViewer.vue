<script setup lang="ts">
import { computed, ref } from "vue";
import type {
  ClauseDiffItem,
  ClauseItem,
  PlaybookClauseEntry,
  TimelineObligationItem,
} from "../api/client";

const props = defineProps<{
  clause: ClauseItem | null;
  playbookEntry: PlaybookClauseEntry | null;
  diffItem: ClauseDiffItem | null;
  decision: "accepted" | "rejected" | "pending";
  obligations: TimelineObligationItem[];
}>();

const emit = defineEmits<{
  (e: "acceptRedline", clauseId: string, tier: "standard" | "fallback"): void;
  (e: "rejectRedline", clauseId: string): void;
}>();

const selectedTier = ref<"standard" | "fallback">("standard");

const proposedText = computed(() => {
  if (props.playbookEntry) {
    return selectedTier.value === "standard"
      ? props.playbookEntry.standard_position
      : props.playbookEntry.fallback_position;
  }
  if (props.diffItem?.revised_text) {
    return props.diffItem.revised_text;
  }
  return props.clause?.redline_suggestion ?? "No redline required — clause aligns with firm standard.";
});

const clauseObligations = computed(() => {
  if (!props.clause) return [];
  const target = props.clause.title.trim().toLowerCase();
  return props.obligations.filter((o) => o.clause_title.trim().toLowerCase() === target);
});
</script>

<template>
  <section class="redline-studio-pane">
    <div v-if="!clause" class="empty-paper">
      <div class="empty-seal">§</div>
      <h3>Select a Clause from the Navigator</h3>
      <p>
        Inspect counterparty language side-by-side against our Law Firm Redline Playbook,
        review extracted SLA/notice deadlines, and accept or reject proposed redlines.
      </p>
    </div>

    <template v-else>
      <header class="pane-header">
        <div>
          <div class="pane-eyebrow">
            <span>{{ clause.clause_type.replace("_", " ").toUpperCase() }}</span>
            <span>·</span>
            <span>RISK SCORE {{ clause.risk_score.toFixed(2) }}</span>
            <span v-if="clause.matched_regulations.length">
              · {{ clause.matched_regulations.join(", ") }}
            </span>
          </div>
          <h2>{{ clause.title }}</h2>
        </div>

        <div class="decision-controls">
          <span :class="['status-badge', decision]">
            {{
              decision === "accepted"
                ? "Redline Accepted"
                : decision === "rejected"
                  ? "Rejected · GC Escalation"
                  : "Pending Counsel Review"
            }}
          </span>
          <button
            class="btn-accept"
            @click="emit('acceptRedline', clause.id, selectedTier)"
          >
            ✓ Accept Redline
          </button>
          <button
            class="btn-reject"
            @click="emit('rejectRedline', clause.id)"
          >
            ✕ Reject
          </button>
        </div>
      </header>

      <div v-if="playbookEntry" class="playbook-toolbar">
        <span class="toolbar-label">Playbook Fallback Tier:</span>
        <button
          :class="['tier-btn', { active: selectedTier === 'standard' }]"
          @click="selectedTier = 'standard'"
        >
          Firm Standard Position
        </button>
        <button
          :class="['tier-btn', { active: selectedTier === 'fallback' }]"
          @click="selectedTier = 'fallback'"
        >
          Negotiated Fallback Position
        </button>
        <span class="walkaway-note">
          <strong>Walk-Away Trigger:</strong> {{ playbookEntry.walk_away_trigger }}
        </span>
      </div>

      <div class="split-paper">
        <article class="paper-column original">
          <div class="column-head">
            <span class="col-tag counterparty">COUNTERPARTY DRAFT (ORIGINAL)</span>
            <span :class="['risk-chip', clause.risk_level]">{{ clause.risk_level }}</span>
          </div>
          <div class="legal-prose">
            <p class="del-highlight">{{ clause.text }}</p>
          </div>
          <div v-if="clause.redline_suggestion" class="risk-callout">
            <strong>Detected Exposure:</strong> {{ clause.redline_suggestion }}
          </div>
        </article>

        <article class="paper-column redlined">
          <div class="column-head">
            <span class="col-tag firm">
              {{
                playbookEntry
                  ? `FIRM REDLINE (${selectedTier.toUpperCase()})`
                  : "REVISED / REDLINE POSITION"
              }}
            </span>
            <span class="col-id">{{ playbookEntry?.id ?? clause.id }}</span>
          </div>
          <div class="legal-prose">
            <p class="ins-highlight">{{ proposedText }}</p>
          </div>
          <div v-if="playbookEntry" class="rationale-callout">
            <strong>Counsel Rationale:</strong> {{ playbookEntry.rationale }}
          </div>
        </article>
      </div>

      <div v-if="clauseObligations.length" class="clause-obligations">
        <h4>Extracted Deadlines &amp; Covenants in this Clause</h4>
        <div class="obl-grid">
          <div v-for="obl in clauseObligations" :key="obl.id" class="obl-chip">
            <div class="obl-top">
              <strong>{{ obl.deadline_label }}</strong>
              <span class="obl-cat">{{ obl.category.replace("_", " ") }}</span>
            </div>
            <p>{{ obl.summary }}</p>
            <small>Party: {{ obl.party }} · Due: {{ obl.due_date_iso ?? "Ongoing" }}</small>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.redline-studio-pane {
  background: #ffffff;
  border: 1px solid #e2ddd2;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(30, 41, 59, 0.05);
}

.empty-paper {
  padding: 56px 32px;
  text-align: center;
  color: #475569;
  background: #faf8f5;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

.empty-seal {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  border: 2px solid #991b1b;
  color: #991b1b;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 22px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
}

.empty-paper h3 {
  margin: 0 0 8px;
  font-family: Georgia, "Times New Roman", serif;
  color: #1e293b;
}

.empty-paper p {
  max-width: 460px;
  font-size: 13px;
  line-height: 1.6;
  margin: 0;
}

.pane-header {
  padding: 16px 20px;
  border-bottom: 1px solid #e7e2d8;
  background: #f5f2eb;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
  flex-wrap: wrap;
}

.pane-eyebrow {
  display: flex;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: #991b1b;
}

.pane-header h2 {
  margin: 4px 0 0;
  font-size: 18px;
  font-family: Georgia, "Times New Roman", serif;
  color: #1e293b;
}

.decision-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.status-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 999px;
}

.status-badge.pending {
  background: #e2e8f0;
  color: #334155;
}

.status-badge.accepted {
  background: #dcfce7;
  color: #166534;
}

.status-badge.rejected {
  background: #fee2e2;
  color: #991b1b;
}

.btn-accept,
.btn-reject {
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid transparent;
}

.btn-accept {
  background: #166534;
  color: #ffffff;
}

.btn-accept:hover {
  background: #14532d;
}

.btn-reject {
  background: #ffffff;
  color: #991b1b;
  border-color: #991b1b;
}

.btn-reject:hover {
  background: #fef2f2;
}

.playbook-toolbar {
  padding: 10px 20px;
  background: #faf8f5;
  border-bottom: 1px solid #e7e2d8;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}

.toolbar-label {
  font-weight: 600;
  color: #475569;
}

.tier-btn {
  background: #ffffff;
  border: 1px solid #d6cfc2;
  color: #1e293b;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}

.tier-btn.active {
  background: #1e293b;
  color: #ffffff;
  border-color: #1e293b;
}

.walkaway-note {
  margin-left: auto;
  color: #991b1b;
  font-size: 11px;
}

.split-paper {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  background: #faf8f5;
}

.paper-column {
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.paper-column.original {
  border-right: 1px solid #e7e2d8;
}

.column-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.col-tag {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.col-tag.counterparty {
  color: #991b1b;
}

.col-tag.firm {
  color: #166534;
}

.col-id {
  font-size: 11px;
  color: #64748b;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.risk-chip {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 999px;
}

.risk-chip.critical {
  background: #fee2e2;
  color: #991b1b;
}

.risk-chip.high {
  background: #ffedd5;
  color: #9a3412;
}

.risk-chip.medium {
  background: #fef3c7;
  color: #92400e;
}

.risk-chip.low {
  background: #dcfce7;
  color: #166534;
}

.legal-prose {
  background: #ffffff;
  border: 1px solid #e7e2d8;
  border-radius: 8px;
  padding: 16px;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 14px;
  line-height: 1.7;
  color: #1e293b;
  min-height: 140px;
}

.del-highlight {
  margin: 0;
  background: rgba(153, 27, 27, 0.06);
  border-left: 3px solid #991b1b;
  padding: 6px 10px;
}

.ins-highlight {
  margin: 0;
  background: rgba(22, 101, 52, 0.06);
  border-left: 3px solid #166534;
  padding: 6px 10px;
}

.risk-callout {
  background: #fef2f2;
  border-left: 3px solid #991b1b;
  padding: 8px 12px;
  font-size: 12px;
  color: #7f1d1d;
  border-radius: 0 6px 6px 0;
}

.rationale-callout {
  background: #f0fdf4;
  border-left: 3px solid #166534;
  padding: 8px 12px;
  font-size: 12px;
  color: #14532d;
  border-radius: 0 6px 6px 0;
}

.clause-obligations {
  padding: 14px 20px;
  border-top: 1px solid #e7e2d8;
  background: #f5f2eb;
}

.clause-obligations h4 {
  margin: 0 0 10px;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #475569;
}

.obl-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}

.obl-chip {
  background: #ffffff;
  border: 1px solid #e2ddd2;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 12px;
}

.obl-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  color: #991b1b;
}

.obl-cat {
  font-size: 10px;
  text-transform: uppercase;
  font-weight: 700;
  color: #475569;
}

.obl-chip p {
  margin: 0 0 4px;
  color: #1e293b;
  line-height: 1.4;
}

.obl-chip small {
  color: #64748b;
}
</style>
