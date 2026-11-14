<script setup lang="ts">
import type { ClauseItem, TimelineObligationItem } from "../api/client";

const props = defineProps<{
  clauses: ClauseItem[];
  obligations: TimelineObligationItem[];
  selectedClauseId: string | null;
  decisions: Record<string, "accepted" | "rejected" | "pending">;
}>();

const emit = defineEmits<{
  (e: "selectClause", clauseId: string): void;
}>();

function obligationsForClause(clauseTitle: string): TimelineObligationItem[] {
  const normalized = clauseTitle.trim().toLowerCase();
  return props.obligations.filter(
    (obl) => obl.clause_title.trim().toLowerCase() === normalized
  );
}

function riskClass(level: string): string {
  switch (level) {
    case "critical":
      return "risk-pill critical";
    case "high":
      return "risk-pill high";
    case "medium":
      return "risk-pill medium";
    default:
      return "risk-pill low";
  }
}

function decisionLabel(clauseId: string): string {
  const status = props.decisions[clauseId] ?? "pending";
  if (status === "accepted") return "Accepted";
  if (status === "rejected") return "Rejected";
  return "Review";
}
</script>

<template>
  <aside class="navigator-panel">
    <div class="nav-header">
      <div>
        <span class="nav-eyebrow">DOCUMENT OUTLINE</span>
        <h3>Clause &amp; Risk Navigator</h3>
      </div>
      <span class="nav-count">{{ clauses.length }} Clauses</span>
    </div>

    <div v-if="clauses.length === 0" class="nav-empty">
      Run <strong>Analyze &amp; Redline</strong> to populate the clause-by-clause outline and obligation badges.
    </div>

    <ul v-else class="clause-outline">
      <li
        v-for="(cl, idx) in clauses"
        :key="cl.id"
        :class="['outline-item', { active: selectedClauseId === cl.id }]"
        @click="emit('selectClause', cl.id)"
      >
        <div class="outline-top">
          <span class="outline-index">§{{ idx + 1 }}</span>
          <span :class="riskClass(cl.risk_level)">{{ cl.risk_level }}</span>
        </div>

        <div class="outline-title">{{ cl.title }}</div>

        <div class="outline-meta">
          <span class="type-tag">{{ cl.clause_type.replace("_", " ") }}</span>
          <span :class="['decision-tag', decisions[cl.id] ?? 'pending']">
            {{ decisionLabel(cl.id) }}
          </span>
        </div>

        <div v-if="obligationsForClause(cl.title).length" class="deadline-badges">
          <span
            v-for="obl in obligationsForClause(cl.title)"
            :key="obl.id"
            :class="['deadline-badge', obl.severity]"
            :title="obl.summary"
          >
            ⏱ {{ obl.deadline_label }} · {{ obl.category.replace("_", " ") }}
          </span>
        </div>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.navigator-panel {
  background: #ffffff;
  border: 1px solid #e2ddd2;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(30, 41, 59, 0.05);
}

.nav-header {
  padding: 14px 16px;
  border-bottom: 1px solid #e7e2d8;
  background: #f5f2eb;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.nav-eyebrow {
  display: block;
  font-size: 10px;
  letter-spacing: 0.08em;
  font-weight: 700;
  color: #991b1b;
}

.nav-header h3 {
  margin: 2px 0 0;
  font-size: 15px;
  font-family: Georgia, "Times New Roman", serif;
  color: #1e293b;
}

.nav-count {
  font-size: 11px;
  font-weight: 600;
  color: #475569;
  background: #eae5da;
  padding: 3px 9px;
  border-radius: 999px;
}

.nav-empty {
  padding: 24px 16px;
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
}

.clause-outline {
  list-style: none;
  margin: 0;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 620px;
  overflow-y: auto;
}

.outline-item {
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid #ece7dc;
  background: #faf8f5;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.outline-item:hover {
  border-color: #cbd5e1;
  background: #f5f1e8;
}

.outline-item.active {
  border-color: #991b1b;
  background: #fffdfb;
  box-shadow: inset 3px 0 0 #991b1b;
}

.outline-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.outline-index {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
}

.outline-title {
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
  line-height: 1.35;
  margin-bottom: 6px;
}

.outline-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
}

.type-tag {
  font-size: 11px;
  color: #475569;
  text-transform: capitalize;
}

.decision-tag {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 4px;
  text-transform: uppercase;
}

.decision-tag.accepted {
  background: #dcfce7;
  color: #166534;
}

.decision-tag.rejected {
  background: #fee2e2;
  color: #991b1b;
}

.decision-tag.pending {
  background: #f1f5f9;
  color: #475569;
}

.risk-pill {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 2px 7px;
  border-radius: 999px;
}

.risk-pill.critical {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fca5a5;
}

.risk-pill.high {
  background: #ffedd5;
  color: #9a3412;
  border: 1px solid #fdba74;
}

.risk-pill.medium {
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #fcd34d;
}

.risk-pill.low {
  background: #dcfce7;
  color: #166534;
  border: 1px solid #86efac;
}

.deadline-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}

.deadline-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f1f5f9;
  color: #1e293b;
  border: 1px solid #cbd5e1;
}

.deadline-badge.critical {
  background: #fef2f2;
  color: #991b1b;
  border-color: #fecaca;
}

.deadline-badge.high {
  background: #fff7ed;
  color: #9a3412;
  border-color: #fed7aa;
}
</style>
