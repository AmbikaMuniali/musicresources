# -*- coding: utf-8 -*-
"""
Ce script analyse une page d'une partition en notation "Tonic Solfa" depuis un fichier PDF.
Il sépare les lignes de notes des lignes de paroles, identifie jusqu'à 4 voix,
et génère un fichier JSON structuré, préformaté pour une conversion en MusicXML.

Ce script a été mis à jour pour :
1.  Créer un DataFrame pandas avec les coordonnées et le texte de chaque élément.
2.  Classifier chaque ligne comme 'notes' ou 'lyrics' en se basant sur la présence
    de caractères spécifiques avant de classer les éléments individuels.
3.  Générer un fichier HTML pour visualiser le DataFrame avec un style dynamique, incluant
    le décalage des symboles et des flèches pour lier les notes.
4.  Générer un fichier JSON avec la même structure que le code initial, mais avec une gestion améliorée.
5.  Prendre en compte la position relative des signes d'octave (ligne supérieure ou inférieure).
"""

# Importation des bibliothèques nécessaires
from PyPDF2 import PdfReader
import pandas as pd
import os
import json
import re
import numpy as np

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

# --- Fonctions pour le traitement et l'analyse ---

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

def classify_and_annotate_text(df: pd.DataFrame) -> pd.DataFrame:
    """
    Classifie les lignes entières avant de classer chaque élément de texte.
    Une ligne est classée comme 'notes', 'octave' ou 'lyrics'.
    Ensuite, les éléments individuels d'une ligne de notes sont séparés et annotés.
    """
    print("Classification et annotation des textes...")
    lines_df = df.groupby('y').agg({
        'text': ' '.join,
        'x': 'first'
    }).reset_index().sort_values(by='y', ascending=False)
    
    new_data = []
    
    note_id_counter = 0
    rhythm_id_counter = 0
    octave_id_counter = 0

    note_line_regex = r'[drmfslt-]'
    octave_line_regex = r'^[0-9│\s]+$' # Ligne ne contenant que des chiffres, '|' et espaces

    for _, line in lines_df.iterrows():
        line_text = line['text']
        y_coord = line['y']
        
        line_type = 'lyric'
        if re.search(note_line_regex, line_text, re.IGNORECASE):
            line_type = 'note'
        elif re.search(octave_line_regex, line_text):
            line_type = 'octave'

        # Pour les lignes de paroles, on les ajoute telles quelles
        if line_type == 'lyric':
            new_data.append({
                'text': line_text,
                'x': line['x'],
                'y': y_coord,
                'type': 'lyric',
                'id': ''
            })
        else:
            # Pour les lignes de notes ou d'octave, on analyse chaque mot
            line_elements = df[df['y'] == y_coord].sort_values(by='x').to_dict('records')
            
            note_regex = r'[drmfslt-]'  # Les notes solfa
            octave_regex = r'[│0-9]'    # Les chiffres sont des octaves
            rhythm_regex = r'[:.,|]'    # Les symboles de rythme

            combined_regex = f"({octave_regex}|{note_regex}|{rhythm_regex})"
            
            for elem in line_elements:
                text_to_process = elem['text'].strip()
                
                if not text_to_process:
                    continue

                # On ne découpe que les lignes de notes/octave
                if line_type == 'note':
                    matches = list(re.finditer(combined_regex, text_to_process, re.IGNORECASE))
                    if matches:
                        last_pos = 0
                        for match in matches:
                            preceding_text = text_to_process[last_pos:match.start()].strip()
                            if preceding_text:
                                # Le texte avant une note est considéré comme lyric
                                new_data.append({
                                    'text': preceding_text,
                                    'x': elem['x'],
                                    'y': elem['y'],
                                    'type': 'lyric',
                                    'id': ''
                                })
                            
                            matched_text = match.group(0)
                            
                            if re.search(note_regex, matched_text, re.IGNORECASE) or matched_text == '-':
                                note_id_counter += 1
                                new_data.append({
                                    'text': matched_text,
                                    'x': elem['x'],
                                    'y': elem['y'],
                                    'type': 'note',
                                    'id': f"note_{note_id_counter}"
                                })
                            elif re.search(rhythm_regex, matched_text):
                                rhythm_id_counter += 1
                                new_data.append({
                                    'text': matched_text,
                                    'x': elem['x'],
                                    'y': elem['y'],
                                    'type': 'rhythm',
                                    'id': f"rhythm_{rhythm_id_counter}"
                                })
                            else: # Fallback to lyric
                                new_data.append({
                                    'text': matched_text,
                                    'x': elem['x'],
                                    'y': elem['y'],
                                    'type': 'lyric',
                                    'id': ''
                                })
                            
                            last_pos = match.end()

                        remaining_text = text_to_process[last_pos:].strip()
                        if remaining_text:
                            new_data.append({
                                'text': remaining_text,
                                'x': elem['x'],
                                'y': elem['y'],
                                'type': 'lyric',
                                'id': ''
                            })
                    else:
                         new_data.append({
                            'text': text_to_process,
                            'x': elem['x'],
                            'y': elem['y'],
                            'type': 'lyric',
                            'id': ''
                        })
                
                elif line_type == 'octave':
                    octave_id_counter += 1
                    new_data.append({
                        'text': text_to_process,
                        'x': elem['x'],
                        'y': elem['y'],
                        'type': 'octave',
                        'id': f"octave_{octave_id_counter}"
                    })

    df_final = pd.DataFrame(new_data)
    print("Classification terminée.")
    return df_final


def associate_symbols_to_notes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Associe les symboles de rythme et d'octave aux notes.
    """
    print("Association des symboles aux notes...")
    df_copy = df.copy()
    df_copy['associated_id'] = None
    
    # Trouver toutes les notes et leurs positions
    notes = df_copy[df_copy['type'] == 'note'].to_dict('records')
    
    # Parcourir chaque élément pour trouver ses associations
    for index, row in df_copy.iterrows():
        if row['type'] in ['rhythm', 'continuation']:
            # Pour les rythmes et continuations, trouver la note la plus proche à gauche sur la même ligne
            closest_note = None
            min_dist_x = float('inf')
            
            for note in notes:
                if note['y'] == row['y'] and note['x'] < row['x']:
                    dist_x = row['x'] - note['x']
                    if dist_x < min_dist_x:
                        min_dist_x = dist_x
                        closest_note = note
            
            if closest_note:
                df_copy.loc[index, 'associated_id'] = closest_note['id']
                
        elif row['type'] == 'octave':
            # Pour les octaves, trouver la note la plus proche (proximité verticale)
            closest_note = None
            min_dist_y = float('inf')
            
            for note in notes:
                dist_y = abs(row['y'] - note['y'])
                if dist_y < min_dist_y:
                    min_dist_y = dist_y
                    closest_note = note
                    
            if closest_note:
                df_copy.loc[index, 'associated_id'] = closest_note['id']
                
    print("Association terminée.")
    return df_copy


def generate_html_from_dataframe(df: pd.DataFrame, page_title: str):
    """
    Génère un fichier HTML pour afficher le texte sur un canvas avec des couleurs
    basées sur la classification.
    """
    print("Génération du fichier HTML...")

    df_json = df.to_json(orient='records')
    
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
        canvas {{ border: 1px solid #ddd; display: block; margin: 0 auto; }}
        .octave-text {{ font-size: 8px; vertical-align: super; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Analyse de la partition : {page_title}</h1>
        <canvas id="partitionCanvas"></canvas>
    </div>

    <script>
        const canvas = document.getElementById('partitionCanvas');
        const ctx = canvas.getContext('2d');
        const dfData = {df_json};

        const colors = {{
            'note': 'black',
            'rhythm': 'green',
            'octave': 'blue',
            'lyric': 'red'
        }};

        function drawText() {{
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.font = '10px sans-serif';
            ctx.textAlign = 'left';

            const maxX = Math.max(...dfData.map(item => item.x)) || 0;
            const maxY = Math.max(...dfData.map(item => item.y)) || 0;
            const minX = Math.min(...dfData.map(item => item.x)) || 0;
            const minY = Math.min(...dfData.map(item => item.y)) || 0;

            const padding = 20;
            canvas.width = (maxX - minX) + 2 * padding;
            canvas.height = (maxY - minY) + 2 * padding;

            const xOffset = -minX + padding;
            const yOffset = -minY + padding;

            dfData.forEach(item => {{
                const y_adjusted = canvas.height - (item.y + yOffset);
                let x_adjusted = item.x + xOffset;
                
                ctx.fillStyle = colors[item.type] || 'black';
                
                // Si c'est une octave, ajuster la taille
                if (item.type === 'octave') {{
                    ctx.font = '8px sans-serif';
                    ctx.fillText(item.text, x_adjusted, y_adjusted);
                    ctx.font = '10px sans-serif'; // Réinitialiser la taille pour le prochain élément
                }} else {{
                    ctx.fillText(item.text, x_adjusted, y_adjusted);
                }}
            }});
        }}
        
        drawText();

        window.addEventListener('resize', drawText);
    </script>
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
            "y": row['y'],
            "type": row['type'],
            "id": row['id'],
            "associated_id": row['associated_id']
        })
        
    # Classification des lignes
    for y, line_data in lines_dict.items():
        is_notes = any(elem['type'] in ['note', 'rhythm', 'octave'] for elem in line_data['elements'])
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
    print("--- Analyseur de Partition v6 ---")
    
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

    pdf_title = os.path.basename(pdf_path)

    df_coords = extract_text_with_coordinates(pdf_path, page_num)
    
    if df_coords.empty:
        print("L'analyse a échoué. Fin du programme.")
        return

    df_classified = classify_and_annotate_text(df_coords)
    
    df_final = associate_symbols_to_notes(df_classified)

    generate_html_from_dataframe(df_final, pdf_title)
    generate_json_from_dataframe(df_final, pdf_title)

if __name__ == "__main__":
    main()
