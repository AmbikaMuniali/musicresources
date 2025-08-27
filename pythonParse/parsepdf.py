# -*- coding: utf-8 -*-
"""
Ce script analyse une page spécifique d'un fichier PDF, extrait chaque mot avec ses coordonnées (x, y),
et génère un fichier HTML représentant la page sous forme de tableau.
"""

# Importation des bibliothèques nécessaires
from PyPDF2 import PdfReader
import pandas as pd
import os

def parse_pdf_to_html_table(fichier_pdf: str, numero_page: int):
    """
    Analyse une page d'un PDF et la convertit en tableau HTML.

    Args:
        fichier_pdf (str): Le chemin d'accès au fichier PDF.
        numero_page (int): Le numéro de la page à analyser (commençant à 1).
    """
    # --- 1. Vérification des entrées ---
    if not os.path.exists(fichier_pdf):
        print(f"Erreur : Le fichier '{fichier_pdf}' n'a pas été trouvé.")
        return

    try:
        lecteur_pdf = PdfReader(fichier_pdf)
        if not (0 < numero_page <= len(lecteur_pdf.pages)):
            print(f"Erreur : Le numéro de page {numero_page} est invalide. Le PDF a {len(lecteur_pdf.pages)} pages.")
            return
        
        # On sélectionne la page demandée (l'index est base 0)
        page = lecteur_pdf.pages[numero_page - 1]
    except Exception as e:
        print(f"Une erreur est survenue lors de la lecture du PDF : {e}")
        return

    # --- 2. Extraction du texte et des coordonnées ---
    parts = []
    
    # La fonction 'visitor' est appelée pour chaque élément de texte trouvé par PyPDF2
    def visitor_body(text, cm, tm, fontDict, fontSize):
        # tm[4] est la coordonnée x, tm[5] est la coordonnée y
        # On arrondit pour regrouper les textes qui sont sur des lignes très proches
        y = round(tm[5])
        x = round(tm[4])
        if text.strip(): # On ignore les textes vides
            parts.append({'text': text, 'x': x, 'y': y})

    print("Début de l'extraction du texte...")
    page.extract_text(visitor_text=visitor_body)
    print(f"{len(parts)} éléments de texte ont été extraits.")

    if not parts:
        print("Aucun texte n'a pu être extrait de cette page.")
        return

    # --- 3. Structuration des données ---
    # On utilise pandas pour manipuler facilement les données
    df = pd.DataFrame(parts)
    
    # Création d'un tableau croisé dynamique (pivot table) pour avoir les mots en grille
    # Les 'y' deviennent les lignes, les 'x' les colonnes
    try:
        pivot_df = df.pivot_table(index='y', columns='x', values='text', aggfunc=''.join).fillna('')
        # On trie les lignes (y) en ordre décroissant pour que le haut de la page apparaisse en premier
        pivot_df = pivot_df.sort_index(ascending=False)
    except Exception as e:
        print(f"Une erreur est survenue lors de la structuration des données : {e}")
        return

    # --- 4. Génération du fichier HTML ---
    print("Génération du fichier HTML...")
    # On convertit le DataFrame pandas directement en HTML
    html_table = pivot_df.to_html(border=1, na_rep='')

    # Ajout de styles CSS pour une meilleure lisibilité
    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>Page {numero_page} du PDF : {os.path.basename(fichier_pdf)}</title>
        <style>
            body {{ font-family: sans-serif; margin: 20px; }}
            h1 {{ color: #333; }}
            table {{ border-collapse: collapse; width: 100%; font-size: 10px; }}
            th, td {{ border: 1px solid #ddd; padding: 4px; text-align: left; }}
            th {{ background-color: #f2f2f2; font-weight: bold; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            td:first-child, th:first-child {{ font-weight: bold; background-color: #eaf2f8; }}
        </style>
    </head>
    <body>
        <h1>Analyse de la page {numero_page} du fichier : {os.path.basename(fichier_pdf)}</h1>
        {html_table}
    </body>
    </html>
    """

    # --- 5. Sauvegarde du fichier ---
    nom_fichier_sortie = f"page_{numero_page}_parsed.html"
    try:
        with open(nom_fichier_sortie, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Succès ! Le fichier '{nom_fichier_sortie}' a été créé.")
        print(f"Vous pouvez l'ouvrir dans votre navigateur.")
    except Exception as e:
        print(f"Impossible de sauvegarder le fichier HTML : {e}")


def main():
    """
    Fonction principale qui demande les informations à l'utilisateur.
    """
    print("--- Analyseur de PDF vers Tableau HTML ---")
    
    # Boucle pour s'assurer que le chemin du fichier est valide
    while True:
        pdf_path = input("Veuillez entrer le chemin complet du fichier PDF : ")
        if os.path.exists(pdf_path) and pdf_path.lower().endswith('.pdf'):
            break
        else:
            print("Chemin invalide ou le fichier n'est pas un .pdf. Veuillez réessayer.")

    # Boucle pour s'assurer que le numéro de page est un entier valide
    while True:
        try:
            page_num_str = input("Quelle page souhaitez-vous analyser ? (ex: 1) : ")
            page_num = int(page_num_str)
            if page_num > 0:
                break
            else:
                print("Veuillez entrer un numéro de page positif.")
        except ValueError:
            print("Entrée invalide. Veuillez entrer un nombre entier.")
            
    parse_pdf_to_html_table(pdf_path, page_num)


# Point d'entrée du script
if __name__ == "__main__":
    main()
