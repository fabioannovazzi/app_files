/**
 * Execute the bounded ECONS mapping/posting procedure from reviewed phase bindings.
 * Exact identity, checkbox state and arithmetic are mechanical contracts from
 * CR-42. The host model reviews account/tax meaning and supplies current approval.
 */
import { canonicalJson, executeCapability, sha256Text } from './capability_runtime.mjs';

const PHASES = ['select', 'map', 'journal', 'post', 'verify', 'exit'];
const text = (value) => typeof value === 'string' && value.trim().length > 0;
class EconsProcessingError extends Error {}
function need(value, code) { if (!value) throw new EconsProcessingError(code); }
const actions = (phase) => phase.milestones.flatMap((milestone) => milestone.actions);

export function validateEconsProcessingProfile(profile) {
  need(profile?.schema_version === 'econs-processing-profile/v1' && text(profile.complete_status) && text(profile.non_posted_view) &&
    Object.keys(profile.phases ?? {}).length === PHASES.length && PHASES.every((name) => profile.phases[name]), 'invalid_processing_profile');
  let origins;
  for (const name of PHASES) {
    const phase = profile.phases[name];
    need(['discovered', 'validated_local'].includes(phase.status), 'processing_requires_reviewed_discovery');
    const current = canonicalJson([...phase.site.allowed_origins].sort());
    origins ??= current;
    need(current === origins, 'processing_origins_must_match');
    const requiredInputs = ['company-code', 'invoice-id', ...(name === 'select' ? ['line-id', 'checked'] : name === 'map' ? ['anchor-line-id', 'checked'] : [])];
    need(requiredInputs.every((key) => phase.inputs.some((input) => input.name === key && input.required && input.type === (key === 'checked' ? 'boolean' : 'text'))), 'missing_processing_context_inputs');
    need(phase.outputs.every((output) => output.delivery === 'model_and_artifact'), 'processing_outputs_must_be_reviewable');
    const requiredOutputs = name === 'journal' ? ['journal'] : name === 'post' ? ['posting'] : name === 'verify' ? ['company', 'invoices', 'invoice-count'] : [];
    need(requiredOutputs.every((key) => phase.outputs.some((output) => output.name === key) && phase.completion.required_outputs.includes(key)), 'missing_processing_verification_outputs');
    for (const action of actions(phase)) {
      need(['read_only', 'reversible', 'consequential'].includes(action.effect), 'unknown_action_effect');
      need(['click', 'wait_for', 'extract', 'set_checked'].includes(action.operation), 'unsupported_processing_operation');
      if (name === 'post') {
        need(action.operation !== 'set_checked', 'post_must_not_change_mapping');
      } else {
        need(action.effect !== 'consequential' && action.confirmation === 'none', 'consequential_action_outside_post');
        need(['select', 'map'].includes(name) || action.operation !== 'set_checked', 'unexpected_checkbox_write');
      }
    }
  }
  const selection = actions(profile.phases.select).filter((action) => action.operation === 'set_checked');
  need(selection.length === 1 && selection[0].input_ref === 'checked', 'selection_requires_set_checked');
  const mapping = actions(profile.phases.map);
  const checkbox = mapping.findIndex((action) => action.id === 'associate-all');
  const confirmation = mapping.findIndex((action) => action.id === 'confirm-mapping');
  need(checkbox >= 0 && mapping[checkbox].operation === 'set_checked' && mapping[checkbox].input_ref === 'checked' &&
    confirmation > checkbox && mapping[confirmation].operation === 'click', 'mapping_requires_checkbox_then_confirmation');
  const posting = actions(profile.phases.post).filter((action) => action.effect === 'consequential');
  need(posting.length === 1 && posting[0].id === 'confirm-registration' && posting[0].operation === 'click' &&
    posting[0].confirmation === 'action_time', 'posting_requires_exact_confirmation');
}

/** Strict Italian money parsing avoids guessing whether a dot is a decimal. */
export function italianCents(value) {
  need(typeof value === 'string' && /^-?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d{1,2})?$/.test(value), 'invalid_italian_amount');
  const negative = value.startsWith('-');
  const [whole, fraction = ''] = value.replace('-', '').replaceAll('.', '').split(',');
  const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'));
  return negative ? -cents : cents;
}

/** Require the complete independent population before planning any line writes. */
export function planEconsMapping(detail) {
  const lines = detail.lines;
  need(Array.isArray(lines) && lines.length > 0 && typeof detail['line-count'] === 'string' &&
    /^\d+$/.test(detail['line-count']) && Number(detail['line-count']) === lines.length, 'incomplete_line_population');
  need(new Set(lines.map((line) => line['line-id'])).size === lines.length &&
    lines.every((line) => text(line['line-id']) && text(line.description) && text(line['vat-code']) &&
      (typeof line.account === 'string' || line.account === null)), 'incomplete_line_fields');
  lines.forEach((line) => italianCents(line.amount));
  const assigned = lines.filter((line) => text(line.account));
  need(assigned.length > 0 && new Set(assigned.map((line) => line.account)).size === 1, 'discordant_or_missing_accounts');
  need(new Set(lines.map((line) => line['vat-code'])).size === 1, 'different_vat_rates');
  const missing = lines.filter((line) => !text(line.account));
  need(!missing.length || assigned.length >= 2, 'two_concordant_lines_required');
  return { account: assigned[0].account, vat: assigned[0]['vat-code'], anchor: assigned[0]['line-id'],
    lineIds: lines.map((line) => line['line-id']), needsMapping: missing.length > 0 };
}

function identity(record, expected) {
  need(record && ['company-code', 'invoice-id', 'invoice-number', 'supplier'].every((key) => record[key] === expected[key]), 'wrong_company_or_invoice');
}

/** Validate the displayed journal, never compute or apply tax treatment. */
export function verifyEconsJournal(journal, invoice, detail, plan, review) {
  identity(journal, invoice);
  need(review?.approved === true && text(review.reason) && review.company_code === invoice['company-code'] &&
    text(review.treatment_source) && typeof review.vat_nondeductible_percent === 'number' &&
    review.vat_nondeductible_percent >= 0 && review.vat_nondeductible_percent <= 100, 'professional_treatment_review_required');
  need(journal.account === plan.account, 'journal_account_changed');
  const debit = italianCents(journal.debit), credit = italianCents(journal.credit), total = italianCents(journal.total);
  need(debit === credit && debit === total && total > 0n, 'journal_does_not_balance');
  const cost = italianCents(journal.cost), vat = italianCents(journal.vat);
  need(cost + vat === total, 'journal_components_do_not_match');
  if (review.vat_nondeductible_percent === 100) need(cost === total && vat === 0n, 'non_deductible_vat_not_in_cost');
  const sum = detail.lines.reduce((amount, line) => amount + italianCents(line.amount), 0n);
  if (sum !== italianCents(journal.net)) need(text(review.rounding_explanation), 'unexplained_rounding_difference');
}

/**
 * Caller supplies already validated phase files, private storage and a durable
 * save callback. No external action precedes saving an ambiguous-attempt state.
 * An exception after posting is unverified and is never automatically retried.
 */
export async function processEconsInvoice({ tab, profile, invoice, detail, entry, readDetail,
  phaseDirectory, save, reviewJournal, approvePosting, environment = {} }) {
  validateEconsProcessingProfile(profile);
  let dispatched = false;
  let phaseIndex = 0;
  async function phase(name, values) {
    const capability = profile.phases[name];
    const inputs = Object.fromEntries(capability.inputs.map((input) => [input.name, values[input.name]]));
    const result = await executeCapability({ tab, capability, inputs,
      runDirectory: await phaseDirectory(`${name}-${++phaseIndex}`), runId: `econs-${name}-${phaseIndex}`,
      approvedConsequentialActions: name === 'post' ? ['confirm-registration'] : [], environment });
    need(result.result === 'passed', `processing_${name}_failed`);
    entry.evidence.push({ label: `Verifica ${name}`, value: result.receipt_path, source: 'Ricevuta locale del runtime browser' });
    return result.delivered_outputs;
  }
  const values = { ...invoice, checked: true };
  try {
    // Re-read the current invoice: a saved collection is not authority to write.
    const current = await readDetail();
    identity(current.invoice, invoice);
    need(canonicalJson(current) === canonicalJson(detail), 'invoice_changed_since_acquisition');
    const plan = planEconsMapping(current);
    entry.proposed = [{ label: 'Conto e IVA', value: `${plan.account} · ${plan.vat}`, source: 'Righe concordanti della fattura completa' }];
    if (plan.needsMapping) {
      entry.status = 'unverified'; entry.question = 'Verificare il risultato della mappatura prima di ripeterla.';
      entry.outcome = 'Associazione preparata; invio ed esito non ancora confermati.';
      await save();
      for (const id of plan.lineIds) await phase('select', { ...values, 'line-id': id });
      await phase('map', { ...values, 'anchor-line-id': plan.anchor });
      detail = await readDetail();
      identity(detail.invoice, invoice);
      const mapped = planEconsMapping(detail);
      need(detail.invoice.status === profile.complete_status && !mapped.needsMapping && mapped.account === plan.account && mapped.vat === plan.vat &&
        canonicalJson(detail.lines.map((line) => ({ ...line, account: '' }))) === canonicalJson(current.lines.map((line) => ({ ...line, account: '' }))), 'mapping_not_verified');
      entry.actual.push({ label: 'Associazione', value: `${plan.account} · ${plan.vat} · tutte le righe verificate`, source: 'Rilettura completa ECONS dopo Conferma del popup' });
      entry.status = 'pending'; entry.question = ''; entry.outcome = 'Mappatura verificata; registrazione ancora da eseguire.';
      await save();
    }
    const output = await phase('journal', values);
    const journal = output.journal;
    const review = await reviewJournal(structuredClone({ invoice, detail, journal }));
    verifyEconsJournal(journal, invoice, detail, plan, review);
    entry.reason = review.reason;
    entry.evidence.push({ label: 'Trattamento IVA della ditta', value: `${review.vat_nondeductible_percent}% indetraibile · ${review.reason}`, source: review.treatment_source });
    if (review.rounding_explanation) entry.evidence.push({ label: 'Arrotondamento', value: review.rounding_explanation, source: 'Revisione professionale della differenza righe / imponibile' });
    entry.proposed.push(...['account', 'net', 'cost', 'vat', 'total', 'debit', 'credit'].map((key) => ({ label: key, value: journal[key], source: 'Prima nota ECONS prima della registrazione' })));
    // Bind host approval to the exact current journal; callbacks cannot mutate it.
    need(await approvePosting(structuredClone({ invoice, journal, journal_sha256: sha256Text(canonicalJson(journal)), action: 'confirm-registration' })) === true, 'posting_not_approved');
    const currentJournal = (await phase('journal', values)).journal;
    need(canonicalJson(currentJournal) === canonicalJson(journal), 'journal_changed_after_approval');
    entry.status = 'unverified'; entry.question = 'Controllare protocollo e lista Non contab. della stessa ditta prima di qualsiasi nuovo tentativo.';
    entry.outcome = 'Conferma reg. preparata; invio ed esito non ancora confermati.';
    await save();
    dispatched = true;
    const posted = (await phase('post', values)).posting;
    need(posted?.['company-code'] === invoice['company-code'] && posted?.['invoice-id'] === invoice['invoice-id'] && text(posted.protocol), 'missing_posting_protocol');
    entry.posting_reference = posted.protocol;
    await save();
    const verified = await phase('verify', values);
    need(verified.company?.['company-code'] === invoice['company-code'] && verified.company?.view === profile.non_posted_view, 'wrong_posting_verification_context');
    need(Array.isArray(verified.invoices) && typeof verified['invoice-count'] === 'string' && /^\d+$/.test(verified['invoice-count']) &&
      Number(verified['invoice-count']) === verified.invoices.length &&
      verified.invoices.every((item) => text(item['invoice-id'])) &&
      new Set(verified.invoices.map((item) => item['invoice-id'])).size === verified.invoices.length, 'incomplete_posting_verification_population');
    need(!verified.invoices.some((item) => item['invoice-id'] === invoice['invoice-id']), 'invoice_still_non_posted');
    entry.actual.push(...entry.proposed.slice(1), { label: 'Protocollo', value: posted.protocol, source: 'Conferma reg. ECONS e assenza verificata in Non contab. della stessa ditta' });
    entry.status = 'completed'; entry.question = ''; entry.outcome = 'Registrazione verificata; protocollo conservato e documento assente da Non contab. della stessa ditta.';
    await save();
  } catch (error) {
    entry.status = dispatched ? 'unverified' : 'set_aside';
    entry.outcome = dispatched ? 'Registrazione tentata; risultato da riconciliare prima di riprovare.' : 'Documento sospeso; nessuna registrazione eseguita.';
    entry.question = dispatched ? 'Verificare protocollo e stato esterno prima di ripetere Conferma reg.' : 'Verificare mappatura, popolazione completa e trattamento della ditta prima di riprendere.';
    if (error instanceof EconsProcessingError) entry.evidence.push({ label: 'Controllo non superato', value: error.message, source: 'Verifica meccanica ECONS; leggere il dato e la ricevuta indicati' });
    entry.evidence.push({ label: 'Interruzione', value: sha256Text(String(error)), source: 'Impronta errore; nessun contenuto browser grezzo' });
    await save();
    // Leave the failed document through its reviewed reversible return phase.
    // If returning fails, stop the batch instead of acting in an unknown context.
    await phase('exit', values);
  }
  return entry.status;
}
