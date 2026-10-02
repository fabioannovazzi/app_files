# Seguir pruebas y decisiones de un expediente ESG

La explicación y una práctica breve requieren unos 5–8 minutos. El procesamiento y tus preguntas pueden alargar la sesión.

Habla con el docente mediante la voz estándar de Codex. En la conversación de trabajo, abierta en la ventana contigua, la función ejecuta el caso con los archivos preparados y muestra resultados reales. El docente sigue esos resultados: puedes interrumpir, preguntar y cambiar el ritmo.

Utiliza el material preparado para enseñar un primer uso completo. Selecciona 3–4 funciones pertinentes durante la incorporación; después, empieza por lo que el usuario quiera hacer hoy. Adapta el ritmo y las explicaciones. Crea ejemplos personalizados cuando ayuden, con el mismo workflow y entradas revisadas. Lee execution-request.json, utiliza el caso local realmente vinculado y explica los resultados verificados de la conversación de trabajo. No inventes resultados, respuestas del usuario ni confirmaciones de comprensión. Abrir el kit no completa la lección.

## 1. Cuándo utilizarla · 45 s

Relaciona la función con una tarea profesional concreta.

Relacionar un valor con su fuente, preparar un borrador parcial e identificar qué debe revisarse después de una actualización.

Caso totalmente ficticio: Officina Selce, un centro y consumo eléctrico declarado de 2026. Primero 0 kWh; corrección 15 kWh. Ninguna medición certificada.

Base documental ESG en Codex desktop y Work local cuando sea compatible. En Cowork el curso utiliza una sola conversación escrita. Ningún informe ESG completo, cálculo VSME/ESRS o taxonomía, opinión de assurance, firma o envío.

## 2. Archivos y petición · 60 s

Abre los archivos en la ventana de trabajo y muestra cómo pedir el resultado.

Lea brief-es.md y energy.csv. El primer valor es cero; la celda 2025 vacía significa no disponible. El centro excluido se declara no aplicable solo en este caso ficticio; el vacío no lo prueba. Reserve energy-update.csv para el siguiente paso.

Vera, prepare el expediente ficticio Officina Selce 2026. Relacione valores con archivos, distinga cero, ausente y no aplicable, muestre una decisión para revisar y un borrador parcial. Importe después la corrección de 0 a 15 kWh y muestre qué queda obsoleto.

## 3. Ejecutar el trabajo · 105 s

Explica el paso que se está ejecutando y espera su resultado real.

Prepare un cliente didáctico separado mediante Studio Archive, importe la nota y energy.csv e inicie la función actual. Acuerde período, servicio preparation y base unresolved sin elegir una norma automáticamente. Cree el caso synthetic y vincule filas 1, 2 y 3 de kwh.

Muestre original, localizador, interpretación y motivo. Antes de record_decision pida la decisión real del participante sobre estas versiones y dependencias. Sin respuesta, déjela abierta. Toda simulación debe etiquetarse y nunca atribuirse al participante. Prepare memo partial_draft con dependencias exactas sin afirmar conformidad.

Conserve el primer run. Importe energy-update.csv como nueva fuente inmutable e inicie otro run del mismo encargo con entradas antiguas y nuevas. start_case usa el primer previous_context; bind_evidence conserva ID energy y registra 15. En resume_case, energy v1 y decisión/borrador dependientes quedan obsoletos; energy v2 es actual. Ausente y no aplicable siguen separados.

Durante la lección, la conversación de trabajo ejecuta la función y produce el resultado. Si un paso no está disponible, explica qué falta y deja la lección incompleta.

## 4. Utilizar el resultado · 75 s

Abre el documento recién producido y muestra por dónde empezar a leerlo.

esg_state.json con archivos, hashes, celdas, versiones, motivos, decisiones y dependencias; borradores parciales Markdown y JSON.

Ambos contextos Studio Archive, originales e historial, codex_run_review.md e informe legible de lecturas reales del modelo. Se ejecutan en esta sesión, no son resultados suministrados.

Compruebe cliente, período, unidad, alcance y fuente. Cero declarado no prueba consumo realmente nulo. Ausente exige recopilación; no aplicable exige motivo. Revise interpretación y suficiencia. Una corrección invalida decisiones dependientes sin renovarlas. Un nombre declarado no es firma autenticada.

## 5. Parar y comprobar · 45 s

Haz estas comprobaciones en los momentos indicados durante el trabajo.

Antes de decidir, encuentre las tres celdas y explique los distintos estados de los dos vacíos.

Tras corregir, muestre versión actual y decisión/borrador anteriores conservados; identifique qué revisar.

Estas pausas ayudan a aprender a utilizar la función. No son un examen de detalles técnicos.

## 6. Ahora prueba tú · 60 s

Deja que el usuario formule la petición y acompaña su intento.

Con menos guía, use files/practice/ en otro cliente didáctico: Laboratorio Quarzo declara 8 y después 12 kWh. Pida el expediente, distinga vacíos, prepare primer borrador e importe corrección en el mismo encargo. Conserve demo. Exprese su decisión o déjela abierta.

Encuentre 0 y luego 15 kWh en demo, 8 y luego 12 en práctica. Originales e historial siguen legibles; decisión/borrador dependientes necesitan revisión. Ambos null mantienen estados distintos; ningún informe completo u opinión está aprobado.

Repita seleccionando cliente, encargo, período y CSV/textos pertinentes; formule petición y revise fuentes e interpretaciones. Cambios son entradas nuevas del mismo encargo. Guía breve de 5–8 minutos; procesamiento y práctica pueden prolongar. Archivos/progreso quedan locales; las lecturas del modelo entran en su contexto sin anonimización automática.

El kit contiene archivos ficticios y un guion preparado. Los resultados de la demostración y la práctica proceden de nuevas ejecuciones de la función actual.

La biblioteca, el perfil y el progreso permanecen en tu ordenador y no se envían a Mparanza. La voz y los contenidos leídos en la conversación se procesan mediante tu cuenta OpenAI: almacenamiento local no significa inferencia sin conexión.
