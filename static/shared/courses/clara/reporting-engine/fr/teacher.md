# Avant le graphique, le sens des données

Un parcours guidé d'environ 6 minutes et demie. L'activation de la voix, les traitements externes et l'exercice facultatif ne sont pas compris.

Parle avec l'enseignant en utilisant la voix standard de Codex. Dans la seconde conversation, ouverte à côté, examine les fichiers et le résultat. Les conversations restent associées ; tu peux interrompre, demander pourquoi ou ralentir à tout moment.

Utilise ces contenus préparés. Ne réécris pas la leçon et n'invente pas de résultats. Parle brièvement, laisse observer et écoute les réponses réelles. Ne dévoile pas la solution avant l'essai. Les durées comprennent observation et dialogue. Montrer ces fichiers ne valide ni démonstration, ni pratique, ni compréhension dans le suivi local. L'enseignant choisit le workflow pertinent uniquement dans le catalogue de son produit.

## 1. Ton objectif · 45 s

Écoute la demande. Rapproche ce cas d'un travail que tu fais déjà.

Le dataset fictif indique 40 000 EUR de ventes nettes en janvier et 50 000 en février. Il n'a pas de champ Discount séparé. Les notes confirment que Sales comprend déjà les remises : les retrancher encore serait erroné.

Clara, montre l'évolution des ventes et explique les données utilisées.

## 2. Les données de départ · 60 s

Regarde les documents dans l'autre conversation. Repère une donnée utile et une information manquante.

R1 contient deux mois et R2 définit les ventes nettes. Discount est absent comme mesure séparée, pas égal à zéro.

[["2026-01", "40 000 EUR", "Ventes nettes"], ["2026-02", "50 000 EUR", "Ventes nettes"], ["Discount séparé", "Absent", "Déjà compris dans Sales"]]

## 3. La méthode du workflow · 75 s

Suis les trois étapes. Arrête-toi sur la décision qui change le résultat.

Exécute l'intake et lis données, profil et notes. Revois sens, agrégation et rôles Sales, Discount et COGS ; les en-têtes ne suffisent pas.
Choisis une capacité compatible et produis le graphique via l'adapter Clara en conservant demande effective et preuve du résultat.
Ouvre et vérifie valeurs, unités, périodes et conclusion. Réutilise un contrat sémantique stable compatible lors des imports suivants.

## 4. Lire le résultat · 90 s

Ouvre l'exemple dans la seconde conversation. Relie chaque conclusion à sa source.

Les ventes nettes passent de 40 000 à 50 000 EUR : +10 000 EUR, soit +25 %. Remises séparées et coûts ne sont pas disponibles.

[["Janvier", "40 000 EUR", "R1 · ventes nettes"], ["Février", "50 000 EUR", "R1 · ventes nettes"], ["Écart", "+10 000 EUR · +25 %", "Base janvier 40 000 EUR"]]

## 5. Le contrôle essentiel · 75 s

Avant d'afficher la réponse, explique ce que tu vérifierais.

Compatibilité technique et exactitude du sens sont différentes. Des colonnes valides peuvent avoir un mauvais mapping métier.

L'absence de Discount permet-elle d'affirmer qu'aucune remise n'a été accordée ?

Comparer le raisonnement: Non. Sales est net et aucune mesure distincte n'est fournie. L'absence de colonne ne prouve pas l'absence de remises.

## 6. Essayer ensemble · 45 s

Choisis de faire l'exercice maintenant ou de garder l'exemple pour une prochaine mission.

Ajoute mars avec la même définition et vérifie réutilisation du contrat et actualisation du graphique.

Sélectionne CSV, Excel ou Parquet et les notes des métriques. Actual/Budget utilise la route budgétaire propre à Clara dans ce workflow.

Cet exemple pédagogique a été préparé à l'avance. Il ne prouve pas une nouvelle exécution. Les sources et décisions sont fictives ; aucune validation professionnelle n'est implicite. Sur tes propres fichiers, le workflow actuel effectue ses contrôles et conserve les résultats réels.

La bibliothèque, le profil et la progression restent sur ton ordinateur et ne sont pas envoyés à Mparanza. La voix et les contenus lus dans la conversation sont traités par ton compte OpenAI : stockage local ne signifie pas traitement hors ligne.
