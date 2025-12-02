import re
from typing import Dict, List, Tuple

import pandas as pd
import requests
import xml.etree.ElementTree as ET


BASE_URL = "http://export.arxiv.org/api/query"
MAX_RESULTS_PER_PAGE = 100

NAMESPACE = {
    "atom": "http://www.w3.org/2005/Atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}


def _build_query_url(search_query: str, start: int, max_results: int) -> str:
    """Construit l'URL de requête pour l'API ArXiv avec pagination."""
    return (
        f"{BASE_URL}?search_query={search_query}"
        f"&start={start}&max_results={max_results}"
    )


def _fetch_batch(search_query: str, start: int, max_results: int) -> ET.Element:
    """Récupère un batch de résultats ArXiv et retourne la racine XML."""
    url = _build_query_url(search_query, start, max_results)
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    return root


def _parse_entry(entry: ET.Element) -> Dict:
    """Extrait les champs intéressants d'une entrée Atom ArXiv."""
    # Dates
    published_text = entry.find("atom:published", NAMESPACE)
    updated_text = entry.find("atom:updated", NAMESPACE)
    published = published_text.text if published_text is not None else None
    updated = updated_text.text if updated_text is not None else None

    # Année
    year = None
    if published:
        m = re.match(r"(\\d{4})-", published)
        if m:
            year = int(m.group(1))

    # Titre
    title_el = entry.find("atom:title", NAMESPACE)
    title = title_el.text.strip().replace("\\n", " ") if title_el is not None else None

    # Résumé
    summary_el = entry.find("atom:summary", NAMESPACE)
    summary = (
        summary_el.text.strip().replace("\\n", " ") if summary_el is not None else None
    )

    # Auteurs (liste de noms)
    authors = [
        a.find("atom:name", NAMESPACE).text.strip()
        for a in entry.findall("atom:author", NAMESPACE)
        if a.find("atom:name", NAMESPACE) is not None
    ]

    # ID ArXiv (URL) et identifiant court
    id_el = entry.find("atom:id", NAMESPACE)
    id_url = id_el.text if id_el is not None else None
    arxiv_id = None
    if id_url and "arxiv.org/abs/" in id_url:
        arxiv_id = id_url.split("arxiv.org/abs/")[-1]

    # DOI
    doi = None
    for link in entry.findall("atom:link", NAMESPACE):
        if link.get("title") == "doi":
            doi = link.get("href")

    # Journal ref & catégories
    journal_ref_el = entry.find(
        "atom:arxiv:journal_ref", {**NAMESPACE, "arxiv": "http://arxiv.org/schemas/atom"}
    )
    journal_ref = journal_ref_el.text if journal_ref_el is not None else None

    categories = [
        c.get("term") for c in entry.findall("atom:category", NAMESPACE) if c.get("term")
    ]

    return {
        "arxiv_id": arxiv_id,
        "id_url": id_url,
        "title": title,
        "summary": summary,
        "authors": ", ".join(authors),
        "published": published,
        "updated": updated,
        "year": year,
        "doi": doi,
        "journal_ref": journal_ref,
        "categories": ", ".join(categories),
    }


def search_arxiv(search_query: str, max_results: int) -> List[Dict]:
    """Recherche générique sur ArXiv et renvoie une liste de dicts."""
    entries: List[Dict] = []
    start = 0

    while start < max_results:
        batch_size = min(MAX_RESULTS_PER_PAGE, max_results - start)
        root = _fetch_batch(search_query, start, batch_size)
        batch_entries = root.findall("atom:entry", NAMESPACE)

        if not batch_entries:
            break

        for entry in batch_entries:
            entries.append(_parse_entry(entry))

        if len(batch_entries) < batch_size:
            break

        start += batch_size

    return entries


def fetch_by_keyword(keyword: str, max_results: int = 200) -> pd.DataFrame:
    """Recherche par mot-clé global (titre, résumé, auteurs, etc.)."""
    query = f"all:{keyword}"
    entries = search_arxiv(query, max_results=max_results)
    return pd.DataFrame(entries)


def _author_to_arxiv_query(author_name: str) -> str:
    """
    Construit une requête auteur simple à partir d'un nom complet.

    Exemple : 'Cassandre Notton' -> 'au:\"Notton_C\"'.
    Ce n'est pas parfait mais couvre la majorité des cas.
    """
    parts = author_name.strip().split()
    if len(parts) < 2:
        # fallback : recherche plein texte sur le nom
        return f"all:\"{author_name}\""
    last = parts[-1]
    first_initial = parts[0][0]
    return f"au:\"{last}_{first_initial}\""


def fetch_by_authors(
    author_names: List[str],
    max_results_per_author: int = 50,
) -> pd.DataFrame:
    """Recherche toutes les publications par une liste d'auteurs."""
    all_entries: List[Dict] = []
    for name in author_names:
        if not isinstance(name, str) or not name.strip():
            continue
        query = _author_to_arxiv_query(name)
        entries = search_arxiv(query, max_results=max_results_per_author)
        all_entries.extend(entries)

    df = pd.DataFrame(all_entries)
    if not df.empty:
        df = df.drop_duplicates(subset=["arxiv_id"])
    return df


def fetch_quandela_related(
    keyword: str,
    author_names: List[str],
    max_results_keyword: int = 200,
    max_results_per_author: int = 50,
) -> pd.DataFrame:
    """
    Combine les publications liées à un mot-clé (ex: 'quandela')
    et celles liées à une liste d'auteurs (Quandelians).
    """
    df_kw = fetch_by_keyword(keyword, max_results=max_results_keyword)
    df_authors = fetch_by_authors(author_names, max_results_per_author=max_results_per_author)

    if df_kw.empty and df_authors.empty:
        return pd.DataFrame()

    frames: List[pd.DataFrame] = []
    if not df_kw.empty:
        df_kw = df_kw.copy()
        df_kw["source"] = "keyword"
        frames.append(df_kw)
    if not df_authors.empty:
        df_authors = df_authors.copy()
        df_authors["source"] = "author"
        frames.append(df_authors)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["year", "title"], ascending=[False, True])
    combined = combined.drop_duplicates(subset=["arxiv_id"])
    return combined


def fetch_paper_by_title(title: str, max_results: int = 5) -> pd.DataFrame:
    """
    Récupère un ou plusieurs papiers à partir d'un titre (ou début de titre).

    Exemple :
        df = fetch_paper_by_title(
            "High-rate entanglement between a semiconductor spin and indistinguishable photons"
        )
    """
    if not title or not isinstance(title, str):
        return pd.DataFrame()

    query = f'ti:"{title}"'
    entries = search_arxiv(query, max_results=max_results)
    return pd.DataFrame(entries)




