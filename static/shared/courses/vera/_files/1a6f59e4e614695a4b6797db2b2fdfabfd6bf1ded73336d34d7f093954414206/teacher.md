# Suivre les preuves et décisions d’un dossier ESG

L’explication et un court exercice prennent environ 5–8 minutes. Le traitement et vos questions peuvent prolonger la séance.

Parlez avec l’enseignant en utilisant la voix standard de Codex. Dans la conversation de travail, ouverte dans la fenêtre voisine, la fonction traite le cas avec les fichiers préparés et affiche ses résultats réels. L’enseignant suit ces résultats : vous pouvez interrompre, poser des questions et changer de rythme.

Utilisez le matériel préparé pour enseigner une première utilisation complète. Choisissez 3–4 fonctions pertinentes lors de l’intégration ; ensuite, partez de ce que l’utilisateur souhaite faire aujourd’hui. Adaptez le rythme et les explications. Créez des exemples personnalisés si cela aide, avec le même workflow et des données vérifiées. Lisez execution-request.json, utilisez le véritable cas local associé et reliez les explications aux résultats vérifiés de la conversation de travail. N’inventez ni résultats, ni réponses de l’utilisateur, ni confirmation de compréhension. Ouvrir le kit ne termine pas la leçon.

## 1. Quand l’utiliser · 45 s

Reliez la fonction à une tâche professionnelle concrète.

Relier une valeur à sa source, préparer un brouillon partiel et repérer les éléments à réexaminer après une mise à jour.

Cas entièrement fictif : Officina Selce, un site et une consommation électrique déclarée pour 2026. Valeur initiale 0 kWh, correction 15 kWh. Aucune mesure certifiée.

Fondation documentaire ESG dans Codex desktop et Work local lorsque pris en charge. Dans Cowork le cours utilise une seule conversation écrite. Aucun rapport ESG complet, calcul VSME/ESRS ou taxonomie, avis d’assurance, signature ou envoi.

## 2. Les fichiers et la demande · 60 s

Ouvrez les fichiers dans la fenêtre de travail et montrez comment demander le résultat.

Lisez brief-fr.md et energy.csv. La première valeur est zéro ; la cellule 2025 vide est indisponible. Le site exclu est déclaré non applicable dans ce seul cas fictif ; le vide ne le prouve pas. Gardez energy-update.csv pour la suite.

Vera, préparez le dossier fictif Officina Selce pour 2026. Reliez les valeurs aux fichiers, distinguez zéro, manquant et non applicable, présentez une décision à examiner et un brouillon partiel. Importez ensuite la correction de 0 à 15 kWh et montrez ce qui devient obsolète.

## 3. Exécuter le travail · 105 s

Expliquez l’étape en cours et attendez son résultat réel.

Préparez un client pédagogique séparé avec Studio Archive, importez la note et energy.csv et démarrez la fonction courante. Convenez de la période, du service preparation et de la base unresolved sans choisir automatiquement une norme. Créez le cas synthetic et liez les lignes 1, 2 et 3 de la colonne kwh.

Montrez original, localisation, interprétation et motif. Avant record_decision, demandez la décision réelle du participant sur ces versions et dépendances. Sans réponse, laissez-la ouverte. Toute simulation doit être étiquetée et jamais attribuée au participant. Produisez un memo partial_draft avec dépendances exactes, sans conformité déclarée.

Conservez le premier run. Importez energy-update.csv comme nouvelle source immuable et démarrez un run suivant dans la même mission avec anciens et nouveaux fichiers. start_case utilise le previous_context initial ; bind_evidence garde l’ID energy et inscrit 15. Dans resume_case, energy v1 et décision/brouillon dépendants sont obsolètes ; energy v2 est courant. Manquant et non applicable restent distincts.

Pendant la leçon, la conversation de travail exécute la fonction et produit le résultat. Si une étape est indisponible, expliquez ce qui manque et laissez la leçon inachevée.

## 4. Utiliser le résultat · 75 s

Ouvrez le document qui vient d’être produit et montrez par où commencer.

esg_state.json : fichiers, empreintes, cellules, versions, motifs, décisions et dépendances ; brouillons partiels Markdown et JSON.

Les deux contextes Studio Archive, originaux et historique, codex_run_review.md et rapport lisible des lectures réelles du modèle. À produire dans la session, pas des résultats fournis.

Vérifiez client, période, unité, périmètre et source. Zéro déclaré ne prouve pas une consommation réellement nulle. Manquant nécessite collecte ; non applicable nécessite justification. Examinez interprétation et suffisance. Une correction invalide les décisions dépendantes sans les renouveler. Un nom déclaré n’est pas une signature authentifiée.

## 5. Faire le point · 45 s

Faites ces vérifications aux moments indiqués pendant le travail.

Avant la décision, retrouvez les trois cellules et expliquez les deux statuts des valeurs vides.

Après correction, montrez version courante et ancienne décision/brouillon conservés ; indiquez quoi réexaminer.

Ces pauses aident à apprendre à utiliser la fonction. Ce ne sont pas des questions sur des détails techniques.

## 6. À vous d’essayer · 60 s

Laissez l’utilisateur formuler la demande et accompagnez son essai.

Avec moins d’aide, utilisez files/practice/ dans un nouveau client pédagogique : Laboratorio Quarzo déclare 8 puis 12 kWh. Demandez le dossier, distinguez les vides, préparez le premier brouillon puis importez la correction dans la même mission. Conservez la démonstration. Exprimez votre décision ou laissez-la ouverte.

Retrouvez 0 puis 15 kWh dans la démonstration, 8 puis 12 dans la pratique. Originaux et historique restent lisibles ; décision/brouillon dépendants demandent réexamen. Les deux null gardent des statuts distincts ; aucun rapport complet ou avis n’est approuvé.

Pour répéter, choisissez client, mission, période et CSV/textes pertinents ; formulez la demande et examinez sources et interprétations. Les mises à jour sont de nouveaux fichiers de la même mission. Guide bref de 5–8 minutes, traitement et pratique peuvent prolonger. Fichiers et progression restent locaux ; les lectures du modèle entrent dans son contexte sans anonymisation automatique.

Le kit contient des fichiers fictifs et un plan préparé. Les résultats de la démonstration et de l’exercice proviennent de nouvelles exécutions de la fonction actuelle.

La bibliothèque, le profil et la progression restent sur votre ordinateur et ne sont pas envoyés à Mparanza. La voix et les contenus lus dans la conversation sont traités par votre compte OpenAI : stockage local ne signifie pas traitement hors ligne.
