import pandas as pd
import streamlit as st
from pathlib import Path

from arxiv_client import fetch_quandela_related


DATA_DIR = Path(".")
ARXIV_CSV = DATA_DIR / "arxiv_quandela_publications.csv"
AUTHORS_CSV = DATA_DIR / "authors_quandela.csv"


def _append_author_to_csv(name: str, short_name: str, is_employee: bool, notes: str) -> None:
    """
    Ajoute un auteur dans authors_quandela.csv (local au container Streamlit).

    Attention : sur Streamlit Community Cloud, cette écriture n'est pas
    répercutée vers GitHub et peut être perdue au redéploiement.
    """
    name = name.strip()
    short_name = short_name.strip() or name.lower().replace(" ", "_")
    notes = notes.strip()

    if not name:
        return

    if AUTHORS_CSV.exists():
        df = pd.read_csv(AUTHORS_CSV)
    else:
        df = pd.DataFrame(
            columns=["name", "short_name", "is_quandela_employee", "notes"]
        )

    # Éviter les doublons exacts sur le nom
    if not df[df["name"] == name].empty:
        return

    new_row = {
        "name": name,
        "short_name": short_name,
        "is_quandela_employee": 1 if is_employee else 0,
        "notes": notes,
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(AUTHORS_CSV, index=False)


@st.cache_data(show_spinner=False)
def load_data(from_arxiv: bool, keyword: str):
    """
    Charge les données :
    - soit depuis ArXiv directement,
    - soit depuis le CSV pré-généré (fallback / mode offline).
    """
    # Liste des auteurs Quandela (référence)
    if AUTHORS_CSV.exists():
        authors_ref = pd.read_csv(AUTHORS_CSV)
    else:
        authors_ref = pd.DataFrame(
            columns=["name", "short_name", "is_quandela_employee", "notes"]
        )

    author_names = (
        authors_ref["name"].dropna().astype(str).tolist() if not authors_ref.empty else []
    )

    if from_arxiv:
        pubs = fetch_quandela_related(keyword=keyword, author_names=author_names)
        if pubs.empty:
            return None, authors_ref, None
    else:
        if not ARXIV_CSV.exists():
            return None, authors_ref, None
        pubs = pd.read_csv(ARXIV_CSV)
        if "authors" not in pubs.columns:
            return None, authors_ref, None

    # Exploser la colonne authors (liste séparée par virgules) en lignes
    exploded = pubs.copy()
    exploded["author_name"] = exploded["authors"].fillna("").astype(str)
    exploded["author_name"] = exploded["author_name"].str.split(",")
    exploded = exploded.explode("author_name")
    exploded["author_name"] = exploded["author_name"].str.strip()

    # Jointure simple sur le nom exact
    merged = exploded.merge(
        authors_ref.rename(columns={"name": "author_name"}),
        on="author_name",
        how="left",
        suffixes=("", "_ref"),
    )

    # Marqueurs logiques
    merged["is_known_author"] = merged["short_name"].notna()
    merged["is_quandela_employee"] = (
        merged["is_quandela_employee"].fillna(0).astype(int)
    )

    return pubs, authors_ref, merged


def main():
    st.set_page_config(page_title="Publications Quandela / Quandelians", layout="wide")

    st.title("📚 Dashboard des publications Quandela & Quandelians")
    st.markdown(
        """
        Ce tableau de bord interroge directement **ArXiv** (ou un CSV local)
        pour lister les publications liées à **Quandela** :

        - via le mot-clé **\"quandela\"**,
        - et via les **auteurs listés dans `authors_quandela.csv`** (Quandelians & collaborateurs).

        Tu peux filtrer par **auteur**, **année** et **type de lien** (employé Quandela ou collaborateur).
        """
    )

    # Panneau latéral de filtres
    st.sidebar.header("Source des données")
    use_live_arxiv = st.sidebar.checkbox(
        "Interroger ArXiv en direct (recommandé)", value=True
    )
    keyword = st.sidebar.text_input("Mot-clé global ArXiv", value="quandela")

    st.sidebar.header("Gestion de la liste d'auteurs")
    with st.sidebar.form("add_author_form", clear_on_submit=True):
        new_name = st.text_input("Nom complet du nouvel auteur")
        new_short = st.text_input("Identifiant court (optionnel)")
        new_is_emp = st.checkbox("Employé Quandela ?", value=True)
        new_notes = st.text_input("Notes (facultatif)")
        submitted_new_author = st.form_submit_button("Ajouter à authors_quandela.csv")

    if submitted_new_author:
        if not new_name.strip():
            st.sidebar.error("Le nom de l'auteur ne peut pas être vide.")
        else:
            _append_author_to_csv(
                name=new_name,
                short_name=new_short,
                is_employee=new_is_emp,
                notes=new_notes,
            )
            # On vide le cache puis on relance l'app pour recharger les données
            load_data.clear()
            st.sidebar.success(f"Auteur ajouté : {new_name}")
            st.experimental_rerun()

    st.sidebar.header("Filtres")

    pubs, authors_ref, merged = load_data(from_arxiv=use_live_arxiv, keyword=keyword)
    if pubs is None or merged is None:
        st.warning(
            "Aucune donnée disponible. Vérifie la connexion internet, le mot-clé ou génère d'abord "
            "`arxiv_quandela_publications.csv` via le notebook."
        )
        return

    # Liste des années disponibles (vue globale)
    if "year" in pubs.columns:
        years = sorted(pubs["year"].dropna().unique())
    else:
        years = []

    selected_years = st.sidebar.multiselect(
        "Années",
        options=years,
        default=years,
    )

    # Liste des auteurs connus (depuis le CSV de référence)
    known_authors = sorted(authors_ref["name"].dropna().unique()) if not authors_ref.empty else []

    selected_authors = st.sidebar.multiselect(
        "Auteurs (liste Quandela / collaborateurs)",
        options=known_authors,
        default=known_authors,
    )

    type_filter = st.sidebar.multiselect(
        "Type de lien avec Quandela",
        options=["Employé Quandela", "Auteur connu (liste)", "Auteur inconnu"],
        default=["Employé Quandela", "Auteur connu (liste)", "Auteur inconnu"],
    )

    search_text = st.sidebar.text_input(
        "Recherche texte (titre ou résumé contient...)",
        value="",
    )

    # Limites globales de dates (pour filtre sur la table détaillée)
    merged_published_dt = pd.to_datetime(merged["published"], errors="coerce")
    min_date = merged_published_dt.min()
    max_date = merged_published_dt.max()
    if pd.isna(min_date) or pd.isna(max_date):
        min_date = None
        max_date = None

    st.sidebar.markdown("**Filtres supplémentaires (table détaillée)**")
    author_substring = st.sidebar.text_input(
        "Nom d'auteur contient...",
        value="",
        help="Filtre sur la colonne `author_name` (contient, insensible à la casse)",
    )
    if min_date and max_date:
        date_range = st.sidebar.date_input(
            "Intervalle de dates (published)",
            (min_date.date(), max_date.date()),
        )
    else:
        date_range = None

    # Préparation du DataFrame détaillé (une ligne = une publication x un auteur)
    df = merged.copy()

    # Compléter la colonne "year" à partir de "published" si besoin
    if "year" not in df.columns or df["year"].isna().any():
        year_from_published = pd.to_datetime(
            df["published"], errors="coerce"
        ).dt.year
        if "year" in df.columns:
            df["year"] = df["year"].fillna(year_from_published)
        else:
            df["year"] = year_from_published

    # Filtre années
    if selected_years:
        df = df[df["year"].isin(selected_years)]

    # Filtre auteurs sélectionnés (uniquement si la liste n'est pas vide)
    if selected_authors:
        df = df[df["author_name"].isin(selected_authors)]

    # Catégorie de lien avec Quandela
    df["relation_type"] = "Auteur inconnu"
    df.loc[df["is_known_author"] == True, "relation_type"] = "Auteur connu (liste)"
    df.loc[df["is_quandela_employee"] == 1, "relation_type"] = "Employé Quandela"

    if type_filter:
        df = df[df["relation_type"].isin(type_filter)]

    # Filtre texte sur titre + résumé
    if search_text.strip():
        mask_title = df["title"].fillna("").str.contains(search_text, case=False, na=False)
        mask_summary = df["summary"].fillna("").str.contains(search_text, case=False, na=False)
        df = df[mask_title | mask_summary]

    # Filtre supplémentaire : auteur contient...
    if author_substring.strip():
        df = df[
            df["author_name"]
            .fillna("")
            .str.contains(author_substring.strip(), case=False, na=False)
        ]

    # Filtre supplémentaire : intervalle de dates published
    if date_range and isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
        df_published_dt = pd.to_datetime(df["published"], errors="coerce")
        mask_date = (df_published_dt.dt.date >= start_date) & (
            df_published_dt.dt.date <= end_date
        )
        df = df[mask_date]

    # Zone de stats globales
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Papiers uniques (après filtres)", df["arxiv_id"].nunique())
    with col2:
        st.metric("Auteurs uniques (lignes détaillées)", df["author_name"].nunique())
    with col3:
        st.metric("Auteurs connus dans la liste", int(df["is_known_author"].sum()))
    with col4:
        st.metric("Auteurs employés Quandela", int((df["is_quandela_employee"] == 1).sum()))

    st.subheader("Tableau détaillé (une ligne = papier × auteur)")

    # Filtres spécifiques à la table (juste au-dessus)
    col_f1, col_f2 = st.columns([1, 2])

    with col_f1:
        years_for_table = sorted(df["year"].dropna().unique()) if "year" in df.columns else []
        selected_years_table = st.multiselect(
            "Années (tableau)",
            options=years_for_table,
            default=years_for_table,
        )

    with col_f2:
        author_filter_table = st.text_input(
            "Filtrer par nom d'auteur (tableau)",
            value="",
        )

    df_table = df.copy()
    if selected_years_table:
        df_table = df_table[df_table["year"].isin(selected_years_table)]
    if author_filter_table.strip():
        df_table = df_table[
            df_table["author_name"]
            .fillna("")
            .str.contains(author_filter_table.strip(), case=False, na=False)
        ]

    display_cols = [
        "year",
        "published",
        "author_name",
        "title",
        "arxiv_id",
        "id_url",
        "doi",
        "categories",
    ]
    for col in display_cols:
        if col not in df_table.columns:
            df_table[col] = None

    st.dataframe(
        df_table[display_cols].sort_values(
            ["year", "author_name", "title"], ascending=[False, True, True]
        ),
        use_container_width=True,
        height=500,
    )

    st.markdown("---")
    st.subheader("Vue agrégée par publication")

    # Regrouper par publication (à partir des données visibles dans le tableau)
    grouped = (
        df_table.groupby(
            ["arxiv_id", "title", "year", "published", "id_url", "doi", "categories"],
            dropna=False,
        )
        .agg(
            authors=("author_name", lambda x: ", ".join(sorted(set(a for a in x if isinstance(a, str) and a.strip())))),
            known_quandela_authors=(
                "author_name",
                lambda x: ", ".join(
                    sorted(
                        set(
                            a
                            for a in x
                            if isinstance(a, str)
                            and a.strip()
                            and a in authors_ref["name"].tolist()
                        )
                    )
                ),
            ),
        )
        .reset_index()
    )

    st.dataframe(
        grouped.sort_values(["year", "title"], ascending=[False, True]),
        use_container_width=True,
        height=500,
    )

    st.markdown("---")
    st.subheader("Publications par année")

    if st.button("Afficher le tableau du nombre de publications par année"):
        pubs_per_year = (
            grouped.groupby("year")["arxiv_id"]
            .nunique()
            .reset_index(name="nombre_de_publications")
            .sort_values("year", ascending=True)
        )

        # Pivot pour avoir les années comme noms de colonnes (1 ligne, N colonnes)
        pubs_per_year_wide = pubs_per_year.set_index("year").T
        pubs_per_year_wide.index = ["nombre_de_publications"]

        st.write("Tableau (1 ligne, colonnes = années) :")
        st.dataframe(
            pubs_per_year_wide,
            use_container_width=True,
        )

        st.write("Graphique du nombre de publications par année :")
        st.bar_chart(
            pubs_per_year.set_index("year")["nombre_de_publications"]
        )

    st.markdown(
        """
        #### Comment mettre à jour la liste des auteurs ?

        **Méthode rapide (depuis le dashboard)**

        - Utilise le formulaire dans la barre latérale **“Gestion de la liste d'auteurs”**.
        - Renseigne :
            - `Nom complet du nouvel auteur` : nom tel qu'il apparaît sur ArXiv,
            - `Identifiant court` (optionnel) : sera généré automatiquement si tu laisses vide,
            - coche ou non **“Employé Quandela ?”**,
            - ajoute éventuellement des `Notes`.
        - Clique sur **“Ajouter à authors_quandela.csv”** : l'auteur est immédiatement pris en compte dans les filtres.

        **Méthode avancée (édition du fichier)**

        - Ouvre le fichier `authors_quandela.csv` dans un éditeur (ou Excel / Google Sheets).
        - Ajoute une ligne par auteur potentiel :
            - `name` : nom tel qu'il apparaît dans ArXiv (exactement, pour que la jointure marche bien),
            - `short_name` : identifiant court (sans espace, pratique pour du code),
            - `is_quandela_employee` : `1` si employé Quandela, `0` sinon,
            - `notes` : commentaires (équipe, rôle, etc.).
        - Sauvegarde, puis **rafraîchis la page Streamlit** (ou laisse l'app se recharger).
        """
    )


if __name__ == "__main__":
    main()


