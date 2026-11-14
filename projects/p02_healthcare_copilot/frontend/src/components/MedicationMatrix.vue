<script setup lang="ts">
import { computed } from "vue";
import type { InteractionCheckResult, OntologyCatalog } from "../api/client";

const props = defineProps<{
  catalog: OntologyCatalog | null;
  activeMeds: string[];
  proposedMeds: string[];
  allergies: string[];
  conditions: string[];
  interactionResult: InteractionCheckResult | null;
  loading?: boolean;
}>();

const emit = defineEmits<{
  (e: "check"): void;
}>();

const selectedMedIds = computed(() => {
  const set = new Set<string>();
  for (const m of props.proposedMeds) {
    if (m.trim()) set.add(m.trim().toLowerCase());
  }
  for (const m of props.activeMeds) {
    if (m.trim()) set.add(m.trim().toLowerCase());
  }
  return Array.from(set);
});

function getPairSeverity(medA: string, medB: string): string | null {
  if (medA === medB) return "self";
  const links = props.catalog?.contraindications ?? [];
  for (const link of links) {
    const s = link.source_med_id.toLowerCase();
    const t = link.target_med_id.toLowerCase();
    if ((s === medA && t === medB) || (s === medB && t === medA)) {
      return link.severity;
    }
  }
  return "safe";
}

function isAllergyMatch(medId: string): boolean {
  if (!props.catalog) return false;
  const med = props.catalog.medications.find(
    (m) => m.med_id.toLowerCase() === medId.toLowerCase()
  );
  if (!med) return false;
  const allergySet = new Set(props.allergies.map((a) => a.trim().toLowerCase()));
  const tags = new Set([
    med.med_id.toLowerCase(),
    med.name.toLowerCase(),
    med.drug_class.toLowerCase(),
    ...med.allergen_tags.map((t) => t.toLowerCase()),
  ]);
  for (const a of allergySet) {
    if (tags.has(a)) return true;
  }
  return false;
}

function isConditionConflict(medId: string): boolean {
  if (!props.catalog) return false;
  const med = props.catalog.medications.find(
    (m) => m.med_id.toLowerCase() === medId.toLowerCase()
  );
  if (!med) return false;
  const condSet = new Set(props.conditions.map((c) => c.trim().toLowerCase()));
  return med.contraindicated_conditions.some((c) => condSet.has(c.toLowerCase()));
}
</script>

<template>
  <section class="matrix-card">
    <div class="matrix-header">
      <div>
        <span class="matrix-kicker">ONTOLOGY SAFETY GUARDRAIL</span>
        <h3>Drug-Drug &amp; Allergy Matrix</h3>
      </div>
      <button
        type="button"
        class="btn-check"
        :disabled="loading"
        @click="emit('check')"
      >
        Verify Safety
      </button>
    </div>

    <div v-if="interactionResult" class="safety-banner" :class="interactionResult.blocked ? 'banner-blocked' : interactionResult.has_conflicts ? 'banner-warn' : 'banner-safe'">
      <strong>{{ interactionResult.blocked ? "⛔ ORDER BLOCKED" : interactionResult.has_conflicts ? "⚠ CAUTION" : "✓ CLEARED" }}</strong>
      <span>{{ interactionResult.summary }}</span>
    </div>

    <div v-if="selectedMedIds.length > 0" class="matrix-table-wrap">
      <table class="matrix-table">
        <thead>
          <tr>
            <th>Med</th>
            <th>Allergy</th>
            <th>Cond.</th>
            <th v-for="col in selectedMedIds" :key="`col-${col}`">{{ col }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in selectedMedIds" :key="`row-${row}`">
            <td class="med-name">
              <span>{{ row }}</span>
              <span v-if="proposedMeds.includes(row)" class="tag-new">NEW</span>
            </td>
            <td class="cell-center">
              <span v-if="isAllergyMatch(row)" class="cell-pill sev-contraindicated">ALLERGY</span>
              <span v-else class="cell-pill sev-safe">OK</span>
            </td>
            <td class="cell-center">
              <span v-if="isConditionConflict(row)" class="cell-pill sev-contraindicated">CONTRA</span>
              <span v-else class="cell-pill sev-safe">OK</span>
            </td>
            <td v-for="col in selectedMedIds" :key="`cell-${row}-${col}`" class="cell-center">
              <span v-if="getPairSeverity(row, col) === 'self'" class="cell-self">—</span>
              <span
                v-else
                class="cell-pill"
                :class="`sev-${getPairSeverity(row, col)}`"
              >
                {{ getPairSeverity(row, col)?.toUpperCase() }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="empty-matrix">
      Add active or proposed medications to inspect the contraindication matrix.
    </div>

    <div v-if="interactionResult && interactionResult.has_conflicts" class="conflict-details">
      <div
        v-for="(ddi, idx) in interactionResult.drug_interactions"
        :key="`ddi-${idx}`"
        class="conflict-item"
      >
        <div class="conflict-title">
          <strong>{{ ddi.med_a }} ↔ {{ ddi.med_b }}</strong>
          <span class="sev-tag" :class="`sev-${ddi.severity}`">{{ ddi.severity }}</span>
        </div>
        <p>{{ ddi.mechanism }}</p>
        <p class="rec">Rec: {{ ddi.recommendation }}</p>
      </div>

      <div
        v-for="(al, idx) in interactionResult.allergy_conflicts"
        :key="`al-${idx}`"
        class="conflict-item"
      >
        <div class="conflict-title">
          <strong>Allergy: {{ al.med_id }} ({{ al.matched_allergies }})</strong>
          <span class="sev-tag sev-contraindicated">{{ al.severity }}</span>
        </div>
        <p class="rec">{{ al.recommendation }}</p>
      </div>

      <div
        v-for="(cc, idx) in interactionResult.condition_conflicts"
        :key="`cc-${idx}`"
        class="conflict-item"
      >
        <div class="conflict-title">
          <strong>Condition: {{ cc.med_id }} ({{ cc.matched_conditions }})</strong>
          <span class="sev-tag sev-contraindicated">{{ cc.severity }}</span>
        </div>
        <p class="rec">{{ cc.recommendation }}</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.matrix-card {
  background: #ffffff;
  border: 1px solid #d8e5f0;
  border-radius: 12px;
  padding: 14px;
  box-shadow: 0 2px 8px rgba(15, 45, 75, 0.04);
}

.matrix-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 10px;
}

.matrix-kicker {
  display: block;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #0284c7;
}

.matrix-header h3 {
  margin: 2px 0 0;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.btn-check {
  background: #0284c7;
  color: #ffffff;
  border: none;
  border-radius: 7px;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.btn-check:hover:not(:disabled) {
  background: #0369a1;
}

.safety-banner {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12px;
  margin-bottom: 10px;
}

.banner-blocked {
  background: #fef2f2;
  border: 1px solid #fca5a5;
  color: #991b1b;
}

.banner-warn {
  background: #fffbeb;
  border: 1px solid #fcd34d;
  color: #92400e;
}

.banner-safe {
  background: #f0fdf4;
  border: 1px solid #86efac;
  color: #166534;
}

.matrix-table-wrap {
  overflow-x: auto;
  margin-bottom: 10px;
}

.matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.matrix-table th,
.matrix-table td {
  border: 1px solid #e2ecf4;
  padding: 5px 6px;
}

.matrix-table th {
  background: #f4f8fb;
  color: #334155;
  font-weight: 700;
  text-transform: uppercase;
  font-size: 10px;
}

.med-name {
  font-weight: 700;
  color: #0f172a;
  display: flex;
  align-items: center;
  gap: 4px;
}

.tag-new {
  font-size: 9px;
  background: #e0f2fe;
  color: #0284c7;
  padding: 1px 4px;
  border-radius: 3px;
}

.cell-center {
  text-align: center;
}

.cell-self {
  color: #94a3b8;
}

.cell-pill,
.sev-tag {
  display: inline-block;
  font-size: 9px;
  font-weight: 700;
  padding: 2px 5px;
  border-radius: 4px;
  text-transform: uppercase;
}

.sev-contraindicated {
  background: #fee2e2;
  color: #b91c1c;
}

.sev-major {
  background: #ffedd5;
  color: #c2410c;
}

.sev-moderate {
  background: #fef3c7;
  color: #b45309;
}

.sev-safe {
  background: #dcfce7;
  color: #15803d;
}

.conflict-details {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.conflict-item {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 8px;
  font-size: 11px;
  color: #334155;
}

.conflict-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 3px;
}

.conflict-item p {
  margin: 2px 0;
}

.conflict-item .rec {
  color: #0f172a;
  font-weight: 600;
}

.empty-matrix {
  font-size: 12px;
  color: #64748b;
  padding: 12px 0;
}
</style>
