"use strict";
const courseCopy = {"it": {"open": "Apri la chat di lavoro", "resume": "Riprendi la chat di lavoro", "description": "Mantieni aperta la chat insegnante. La chat di lavoro usa i file e i progressi salvati di questo corso.", "detail": "L'app può chiederti di confermare la richiesta leggibile. Il lavoro inizia dopo la verifica dell'accesso alla cartella nella chat di lavoro.", "unavailable": "Questo host non supporta il pulsante del corso. Chiedi all'insegnante di aprire la chat di lavoro abbinata con i controlli nativi dell'host.", "confirm": "Conferma la richiesta nell'app…", "received": "Richiesta ricevuta dall'app. La chat di lavoro deve verificare l'incarico salvato prima di iniziare.", "error": "L'invio non è stato confermato. Controlla le chat aperte prima di riprovare."}, "en": {"open": "Open working chat", "resume": "Resume working chat", "description": "Keep the teacher chat open. The working chat uses this course's saved files and progress.", "detail": "The app may ask you to confirm the readable request. Work starts after the working chat verifies access to the course folder.", "unavailable": "This host does not support the course chat button. Ask the teacher to open the paired working chat with native host controls.", "confirm": "Confirm the request in the app…", "received": "Request received by the app. The working chat must verify the saved assignment before starting.", "error": "Sending was not confirmed. Check the open chats before retrying."}, "fr": {"open": "Ouvrir la conversation de travail", "resume": "Reprendre la conversation de travail", "description": "Gardez la conversation avec le formateur ouverte. La conversation de travail utilise les fichiers et la progression enregistrés de ce cours.", "detail": "L’application peut vous demander de confirmer la demande lisible. Le travail commence après vérification de l’accès au dossier du cours.", "unavailable": "Cet environnement ne prend pas en charge ce bouton. Demandez au formateur d’ouvrir la conversation de travail associée avec les commandes natives.", "confirm": "Confirmez la demande dans l’application…", "received": "Demande reçue par l’application. La conversation de travail doit vérifier la tâche enregistrée avant de commencer.", "error": "L’envoi n’a pas été confirmé. Vérifiez les conversations ouvertes avant de réessayer."}, "de": {"open": "Arbeitschat öffnen", "resume": "Arbeitschat fortsetzen", "description": "Lassen Sie den Lernchat geöffnet. Der Arbeitschat verwendet die gespeicherten Dateien und den Fortschritt dieses Kurses.", "detail": "Die App kann Sie bitten, die lesbare Anfrage zu bestätigen. Die Arbeit beginnt nach Prüfung des Zugriffs auf den Kursordner.", "unavailable": "Diese Umgebung unterstützt die Schaltfläche nicht. Bitten Sie den Lernchat, den zugeordneten Arbeitschat über die nativen Funktionen zu öffnen.", "confirm": "Bestätigen Sie die Anfrage in der App…", "received": "Die App hat die Anfrage erhalten. Der Arbeitschat muss den gespeicherten Auftrag vor Beginn prüfen.", "error": "Der Versand wurde nicht bestätigt. Prüfen Sie die offenen Chats, bevor Sie es erneut versuchen."}, "es": {"open": "Abrir el chat de trabajo", "resume": "Reanudar el chat de trabajo", "description": "Mantén abierto el chat del profesor. El chat de trabajo utiliza los archivos y el progreso guardados de este curso.", "detail": "La aplicación puede pedirte que confirmes la solicitud legible. El trabajo empieza después de verificar el acceso a la carpeta del curso.", "unavailable": "Este entorno no admite el botón. Pide al profesor que abra el chat de trabajo vinculado mediante los controles nativos.", "confirm": "Confirma la solicitud en la aplicación…", "received": "La aplicación ha recibido la solicitud. El chat de trabajo debe verificar la tarea guardada antes de empezar.", "error": "El envío no se ha confirmado. Comprueba los chats abiertos antes de volver a intentarlo."}};
const copyFor = data => courseCopy[data.language] || courseCopy.it;
function courseMessage(data) {
  const english = data.language && data.language !== "it";
  const reference = english
    ? `Product: ${data.product}. Course: ${data.workflow_id}. Course folder: ${data.state_root}.`
    : `Prodotto: ${data.product}. Corso: ${data.workflow_id}. Cartella del corso: ${data.state_root}.`;
  const prompt = data.action === "new"
    ? (english ? `${copyFor(data).open}: «${data.title}».\n${reference}\nInvitation: ${data.invitation}.\nUse course_chat_claim with this invitation, this folder and your actual native thread ID. Verify local access and retrieve the saved assignment before executing. Keep the teacher chat ${data.teacher_thread_id} paired. Read the exact installed workflow; perform only the teacher's bounded assignment and return actual artifacts and state. Do not restart the interview or record lesson completion.`
      : `Apri la chat di lavoro per «${data.title}».\n${reference}\nInvito: ${data.invitation}.\nUsa course_chat_claim con questo invito, questa cartella e il tuo vero ID di chat nativa. Verifica l'accesso locale e recupera l'incarico salvato prima di eseguire. Mantieni l'abbinamento con la chat insegnante ${data.teacher_thread_id}. Leggi il workflow installato esatto; esegui solo l'incarico circoscritto dell'insegnante e restituisci file e stato reali. Non ripetere l'intervista e non registrare il completamento della lezione.`)
    : (english ? `${copyFor(data).resume}: «${data.title}».\n${reference}\nWorking chat: ${data.worker_thread_id}. Teacher chat: ${data.teacher_thread_id}.\n${data.session_id ? `Session: ${data.session_id}.\n` : ""}Inspect and reopen this saved native chat using the host tools; restore it if archived. Verify the current course state and each chat's folder access, then continue the current bounded lesson. Do not create a duplicate chat or reset progress. If unavailable, verify that before offering a replacement button.`
      : `Riprendi la chat di lavoro per «${data.title}».\n${reference}\nChat di lavoro: ${data.worker_thread_id}. Chat insegnante: ${data.teacher_thread_id}.\n${data.session_id ? `Sessione: ${data.session_id}.\n` : ""}Controlla e riapri questa chat nativa salvata con gli strumenti dell'host; ripristinala se archiviata. Verifica lo stato corrente del corso e l'accesso alla cartella in entrambe le chat, poi continua la lezione circoscritta corrente. Non creare chat duplicate e non azzerare i progressi. Se non è disponibile, verificalo prima di offrire il pulsante per sostituirla.`);
  return { role: "user", content: [{ type: "text", text: prompt }], _meta: { "openai/message": { target: data.action === "new" ? "new" : "active" } } };
}
if (typeof module !== "undefined") module.exports = { courseMessage };
if (typeof document !== "undefined") (() => {
  const button = document.getElementById("launch");
  const status = document.getElementById("status");
  let data, host, busy = false, sent = false, next = 0;
  const pending = new Map();
  function request(method, params) {
    return new Promise((resolve, reject) => {
      const id = ++next;
      const timer = setTimeout(() => { pending.delete(id); reject(new Error(copyFor(data || {}).error)); }, method === "ui/message" ? 300000 : 30000);
      pending.set(id, { resolve, reject, timer });
      window.parent.postMessage({ jsonrpc: "2.0", id, method, params }, "*");
    });
  }
  function render() {
    if (!data) return;
    const copy = copyFor(data);
    document.documentElement.lang = data.language || "it";
    document.getElementById("product").textContent = data.product[0].toUpperCase()+data.product.slice(1);
    document.getElementById("title").textContent = data.title;
    document.getElementById("description").textContent = copy.description;
    button.textContent = data.action === "new" ? copy.open : copy.resume;
    const supported = !!host?.hostCapabilities?.experimental?.["openai/message"];
    button.disabled = !supported || busy || sent;
    document.getElementById("detail").textContent = supported ? copy.detail : copy.unavailable;
  }
  window.addEventListener("message", event => {
    if (event.source !== window.parent) return;
    const message = event.data;
    if (!message || message.jsonrpc !== "2.0") return;
    const item = pending.get(message.id);
    if (item) { clearTimeout(item.timer); pending.delete(message.id); message.error ? item.reject(new Error(message.error.message)) : item.resolve(message.result); return; }
    if (message.method === "ui/notifications/tool-result" && message.params?._meta?.course_chat) { data = message.params._meta.course_chat; sent = false; render(); }
    if (message.method === "ui/resource-teardown") window.parent.postMessage({ jsonrpc: "2.0", id: message.id, result: {} }, "*");
  });
  button.addEventListener("click", async () => {
    if (busy || sent || button.disabled) return;
    busy = true; render(); status.textContent = copyFor(data).confirm;
    try {
      const result = await request("ui/message", courseMessage(data));
      if (result?.isError) throw new Error(copyFor(data).error);
      sent = true;
      status.textContent = copyFor(data).received;
    } catch (error) { status.textContent = error.message; status.className = "error"; }
    finally { busy = false; render(); }
  });
  request("ui/initialize", { protocolVersion: "2026-01-26", appInfo: { name: "Course chats", version: "1.0.0" }, appCapabilities: {} }).then(result => {
    host = result; render(); window.parent.postMessage({ jsonrpc: "2.0", method: "ui/notifications/initialized" }, "*");
  }).catch(error => { status.textContent = error.message; status.className = "error"; });
})();
