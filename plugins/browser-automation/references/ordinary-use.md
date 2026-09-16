# Ordinary use of a supported browser process

Use this route when the operator asks for professional work to be done using a
supported saved process. Teaching, recording and development are separate intents.
Read `process-lifecycle.md` for the register and executable entry points.

1. Enter through the named operation skill selected by the user or Vera's
   normal skill router. Read that skill's exact scope and adjacent `process.json`
   and `capability.json`. Do not select from the local development catalog.
   If several installed named skills fit, ask which business outcome is intended;
   never substitute an approximate procedure or an unpublished local draft.
2. Call `process_skills.py begin --skill <selected-skill-folder> --input <host>`.
   This imports only that skill's bound process and pins its procedure version.
   It returns the ordinary-use attempt, declared inputs and runtime path, or a
   report explaining the missing verification/support. Publishing the named skill
   does not import another machine's qualification. Existing ECONS/Agenzia
   specialist routes retain their own protections and prototype limitations.
3. Obtain only missing business inputs from the typed declarations and context,
   such as selected client, period and destination. Do not put those values in
   the process description or external feedback. Use the operator's current
   authorization and authentication handoff. Ask at action time for consequential
   actions when required; routine navigation has no repeated consent gate.
4. Observe the current callable browser/local runtime before the bound `begin` call.
   If it reports a block, open its report and explain the exact missing support
   or required retest. Do not silently relabel ordinary use as a test or switch
   to an improvised action sequence. Continue independently useful evidence or
   setup work within the user's request.
5. In the same documented Node session as the connected tab, call:

   ```javascript
   const { executeProcess } = await import(moduleRuntimeUrl);
   const result = await executeProcess({
     attemptDirectory, tab, inputs, currentHost,
     approvedConsequentialActions,
   });
   ```

   Vera resolves `moduleRuntimeUrl` to the installed module's
   `scripts/process_runtime.mjs`; all variables come from its selected process,
   returned attempt, actual host tools and user scope. The accountant does not
   assemble this call. Keep safe recovery within the existing capability
   contract, start a new attempt, and never count recovery as a clean replay.
6. Open the returned report and verify the professional outcome against inputs,
   expected population and saved output evidence. Save its result review. Link
   the readable report and the permitted local outputs. State actual results,
   exceptions, elapsed time and missing measurements; do not claim nonexistent
   model/token telemetry. A passed technical run still needs its result checked.
7. A failure, recovery, incomplete or incorrect result suspends ordinary use for
   that contract/environment. Preserve the attempt, prepare reviewed sanitized
   feedback and reuse the same process identity through CR, repair, release and
   retest. Transmit only within the existing authorization. The same named skill recovers this state in a new conversation; never ask the
   operator to resume an old chat.

Example final result: "Ho salvato 24 XML e verificato il conteggio rispetto alle
24 fatture selezionate. Il report contiene le verifiche e gli eventuali scarti.
Tempo misurato: 48 secondi. I token non sono esposti dall’host."
Those numbers are illustrative: use only the actual run's measured results.
