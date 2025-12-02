## Dashboard publications Quandela (ArXiv + auteurs)

Ce dépôt contient :

- `scraping.ipynb` : notebook de test pour appeler l'API ArXiv.
- `arxiv_client.py` : petit client Python pour ArXiv (recherche par mot-clé, par auteur, par titre).
- `dashboard.py` : application **Streamlit** qui affiche les publications liées à Quandela et aux **Quandelians**.
- `authors_quandela.csv` : liste d'auteurs (employés Quandela et collaborateurs) utilisée pour tagger les papiers.

### 1. Lancer en local

```bash
cd publications_report
pip install -r requirements.txt
streamlit run dashboard.py
```

### 2. Déployer sur Streamlit Community Cloud

1. Pousser ce dossier sur un dépôt GitHub (par ex. `quandela-publications-dashboard`).
2. Aller sur `https://share.streamlit.io` et se connecter avec ton compte GitHub.
3. Cliquer sur **New app** :
   - **Repository** : choisir le dépôt GitHub,
   - **Branch** : `main` (ou celle que tu utilises),
   - **Main file path** : `dashboard.py`.
4. Lancer le déploiement.

Streamlit va automatiquement :

- installer les dépendances listées dans `requirements.txt`,
- lancer `dashboard.py`.

### 3. Mettre à jour la liste des auteurs

Éditer `authors_quandela.csv` (dans GitHub ou en local puis `git push`) et redéployer :

- `name` : nom EXACT tel qu'il apparaît sur ArXiv,
- `short_name` : identifiant court (facultatif, mais pratique),
- `is_quandela_employee` : `1` si employé Quandela, `0` sinon,
- `notes` : remarques libres.

Après mise à jour :

- en local : relancer `streamlit run dashboard.py`,
- sur Streamlit Cloud : cliquer sur **Rerun** ou attendre le redéploiement après `git push`.


