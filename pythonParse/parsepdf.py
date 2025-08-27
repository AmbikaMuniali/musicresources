# -*- coding: utf-8 -*-
"""
Ce script analyse une page d'une partition en notation "Tonic Solfa" depuis un fichier PDF.
Il sépare les lignes de notes des lignes de paroles, identifie jusqu'à 4 voix,
et génère un fichier JSON structuré, préformaté pour une conversion en MusicXML.

Ce script a été mis à jour pour :
1.  Créer un DataFrame pandas avec les coordonnées et le texte de chaque élément.
2.  Classifier chaque ligne comme 'notes' ou 'lyrics'.
3.  Colorer les lignes qui sont à moins de 5 pixels les unes des autres.
4.  Générer un fichier HTML pour visualiser le DataFrame avec un style dynamique.
5.  Générer un fichier JSON avec la même structure que le code initial, mais avec une gestion améliorée.
"""

# Importation des bibliothèques nécessaires
from PyPDF2 import PdfReader
import pandas as pd
import os
import json
import re

# --- Dictionnaires de mapping pour la conversion ---

SOLFA_TO_STEP = {
    'd': 'C', 'r': 'D', 'm': 'E', 'f': 'F',
    's': 'G', 'l': 'A', 't': 'B'
}

RHYTHM_TO_DURATION = {
    '': {'duration': 4, 'type': 'quarter'},
    '.': {'duration': 8, 'type': 'eighth'},
    ',': {'duration': 16, 'type': 'sixteenth'}
}

# --- Nouvelles fonctions pour le traitement et l'analyse ---

def extract_text_with_coordinates(pdf_path: str, page_num: int) -> pd.DataFrame:
    """
    Extrait le texte et les coordonnées de chaque mot de la page spécifiée du PDF
    en utilisant une fonction de visite (visitor).
    """
    print(f"Extraction du texte et des coordonnées de la page {page_num}...")
    try:
        reader = PdfReader(pdf_path)
        page = reader.pages[page_num - 1]
        
        data = []
        
        def visitor_body(text, cm, tm, fontDict, fontSize):
            """
            Fonction de rappel pour capturer le texte et les coordonnées
            """
            # Récupération des coordonnées x et y de la matrice de transformation (tm)
            # tm[4] est la coordonnée x, tm[5] est la coordonnée y
            x = tm[4]
            y = tm[5]
            
            # Ajoutez le texte et les coordonnées à notre liste
            data.append({'text': text.strip(), 'x': x, 'y': y})

        page.extract_text(visitor_text=visitor_body)
        
        # Création du DataFrame
        df = pd.DataFrame(data)
        
        # Nettoyer les entrées vides ou non pertinentes
        df = df[df['text'] != '']
        
        # Grouper les mots en se basant sur la proximité x et y pour former
        # des lignes logiques
        df['x'] = df['x'].round(0).astype(int)
        df['y'] = df['y'].round(0).astype(int)
        df = df.sort_values(by=['y', 'x'], ascending=[False, True]).reset_index(drop=True)
        
        # La fonction visitor_body donne chaque caractère ou segment de texte,
        # nous devons les regrouper en mots logiques.
        processed_data = []
        if not df.empty:
            current_x = df.loc[0, 'x']
            current_y = df.loc[0, 'y']
            current_text = df.loc[0, 'text']
            
            for i in range(1, len(df)):
                next_x = df.loc[i, 'x']
                next_y = df.loc[i, 'y']
                next_text = df.loc[i, 'text']
                
                # Si le mot suivant est proche, on l'ajoute au mot courant
                if abs(next_x - current_x) < 20 and abs(next_y - current_y) < 5:
                    current_text += next_text
                    current_x = next_x
                else:
                    processed_data.append({'text': current_text, 'x': current_x, 'y': current_y})
                    current_x = next_x
                    current_y = next_y
                    current_text = next_text
            
            processed_data.append({'text': current_text, 'x': current_x, 'y': current_y})
            
        df_final = pd.DataFrame(processed_data)
        
        print("Extraction réussie.")
        return df_final
    except Exception as e:
        print(f"Erreur lors de l'extraction du texte : {e}")
        return pd.DataFrame()

def process_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Traite le DataFrame pour ajouter des informations de groupe de ligne,
    de type de ligne et de couleur.
    """
    if df.empty:
        return df
    
    # 1. Grouper les lignes par proximité Y
    df = df.sort_values(by='y', ascending=False).reset_index(drop=True)
    df['line_group'] = 0
    df['line_type'] = ''
    df['color'] = ''
    group_id = 0
    
    if not df.empty:
        df.loc[0, 'line_group'] = group_id
        for i in range(1, len(df)):
            if abs(df.loc[i, 'y'] - df.loc[i-1, 'y']) > 5:
                group_id += 1
            df.loc[i, 'line_group'] = group_id
    
    # Définir les couleurs pour les groupes
    colors = ['#f2f2f2', '#eaf2f8']
    df['color'] = df['line_group'].apply(lambda x: colors[x % 2])
    
    # 2. Classifier chaque ligne comme 'notes' ou 'lyrics'
    grouped_lines = df.groupby('line_group')['text'].apply(list).reset_index()
    
    for index, row in grouped_lines.iterrows():
        line_elements = row['text']
        # Une ligne de notes contient majoritairement des éléments courts (<= 3 caractères)
        is_notes = all(len(word.strip('.,')) <= 3 for word in line_elements)
        line_type = 'notes' if is_notes else 'lyrics'
        df.loc[df['line_group'] == row['line_group'], 'line_type'] = line_type
        
    return df

def generate_html_from_dataframe(df: pd.DataFrame, page_title: str):
    """
    Génère un fichier HTML à partir du DataFrame avec un style dynamique.
    Les coordonnées sont utilisées pour positionner les éléments.
    """
    print("Génération du fichier HTML...")
    
    # Récupérer toutes les coordonnées uniques
    unique_x = sorted(df['x'].unique())
    unique_y = sorted(df['y'].unique(), reverse=True)
    
    # Créer une matrice de mots basée sur les coordonnées
    data_matrix = pd.DataFrame(index=unique_y, columns=unique_x).fillna('')
    for _, row in df.iterrows():
        x_val = row['x']
        y_val = row['y']
        text_val = row['text']
        data_matrix.loc[y_val, x_val] = text_val
        
    # Calculer les largeurs de colonnes
    col_widths = []
    for i in range(len(unique_x)):
        if i < len(unique_x) - 1:
            width = (unique_x[i+1] - unique_x[i]) + 10  # 10px de plus pour l'espacement
        else:
            width = 100 # Largeur par défaut pour la dernière colonne
        col_widths.append(f'{width}px')
    
    col_width_css = ' '.join(col_widths)

    html_content = f"""
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title}</title>
    <style>
        body {{ font-family: sans-serif; margin: 0; padding: 0; background-color: #f4f4f4; }}
        .container {{ max-width: 800px; margin: 20px auto; padding: 20px; background-color: white; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; text-align: center; }}
        .responsive-table {{ overflow-x: auto; }}
        table {{ border-collapse: collapse; font-size: 14px; table-layout: fixed; }}
        th, td {{ padding: 8px; text-align: left; border: 1px solid #ddd; }}
        th {{ background-color: #f2f2f2; font-weight: bold; }}
        .text-cell {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
        col {{ width: 100px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Analyse de la partition : {page_title}</h1>
        <div class="responsive-table">
            <table>
                <colgroup>
                    <col style="width: 50px;"> <!-- Largeur pour la colonne Y/X -->
                    {"".join(f'<col style="width: {w};">' for w in col_widths)}
                </colgroup>
                <thead>
                    <tr>
                        <th>Y/X</th>
                        {"".join(f"<th>{x}</th>" for x in unique_x)}
                    </tr>
                </thead>
                <tbody>
    """
    
    for y_coord, row in data_matrix.iterrows():
        html_content += f"""
        <tr>
            <th>{y_coord}</th>
            {"".join(f'<td class="text-cell" title="{cell}">{cell}</td>' for cell in row)}
        </tr>
        """
    
    html_content += """
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
    """

    nom_fichier_sortie = "partition_analyse.html"
    try:
        with open(nom_fichier_sortie, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"Succès ! Le fichier '{nom_fichier_sortie}' a été créé.")
    except Exception as e:
        print(f"Impossible de sauvegarder le fichier HTML : {e}")

def generate_json_from_dataframe(df: pd.DataFrame, pdf_title: str):
    """
    Génère un fichier JSON structuré à partir du DataFrame.
    """
    print("Génération du fichier JSON...")
    score_data = {
        "title": pdf_title,
        "lines": []
    }
    
    # Créer un dictionnaire pour regrouper les mots par ligne (coordonnée Y)
    lines_dict = {}
    for _, row in df.sort_values(by=['y', 'x'], ascending=[False, True]).iterrows():
        y_val = row['y']
        if y_val not in lines_dict:
            lines_dict[y_val] = {
                "text": [],
                "elements": []
            }
        lines_dict[y_val]["text"].append(row['text'])
        lines_dict[y_val]["elements"].append({
            "text": row['text'],
            "x": row['x'],
            "y": row['y']
        })
        
    # Classification des lignes
    for y, line_data in lines_dict.items():
        is_notes = all(len(word.strip('.,')) <= 3 for word in line_data['text'])
        line_data['type'] = 'notes' if is_notes else 'lyrics'
        line_data['text'] = " ".join(line_data['text'])
        
    score_data["lines"] = list(lines_dict.values())

    nom_fichier_sortie = "partition_analyse.json"
    try:
        with open(nom_fichier_sortie, "w", encoding="utf-8") as f:
            json.dump(score_data, f, ensure_ascii=False, indent=2)
        print(f"Succès ! Le fichier '{nom_fichier_sortie}' a été créé.")
    except Exception as e:
        print(f"Impossible de sauvegarder le fichier JSON : {e}")

def main():
    """
    Fonction principale qui demande les informations à l'utilisateur.
    """
    print("--- Analyseur de Partition v5 ---")
    
    while True:
        pdf_path = input("Veuillez entrer le chemin complet du fichier PDF : ")
        if os.path.exists(pdf_path) and pdf_path.lower().endswith('.pdf'):
            break
        else:
            print("Chemin invalide ou le fichier n'est pas un .pdf. Veuillez réessayer.")

    while True:
        try:
            page_num_str = input("Quelle page de la partition souhaitez-vous analyser ? (ex: 1) : ")
            page_num = int(page_num_str)
            if page_num > 0:
                break
            else:
                print("Veuillez entrer un numéro de page valide (supérieur à 0).")
        except ValueError:
            print("Entrée invalide. Veuillez entrer un numéro.")

    # Nom du fichier pour le titre
    pdf_title = os.path.basename(pdf_path)

    # 1. Extraction du texte et des coordonnées dans un DataFrame
    df_coords = extract_text_with_coordinates(pdf_path, page_num)
    
    if df_coords.empty:
        print("L'analyse a échoué. Fin du programme.")
        return

    # 2. Génération des fichiers de sortie
    generate_html_from_dataframe(df_coords, pdf_title)
    generate_json_from_dataframe(df_coords, pdf_title)

if __name__ == "__main__":
    main()
